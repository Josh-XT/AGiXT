import os
import re
import time
import datetime
import requests
import difflib
from pydantic import BaseModel
from typing import List, Literal, Union
from Extensions import Extensions
from agixtsdk import AGiXTSDK, get_tokens
from Globals import getenv
from dataclasses import dataclass
import logging

try:
    import black
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "black"])
    import black

try:
    import git
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "GitPython"])
    import git

try:
    from github import Github, RateLimitExceededException
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyGithub"])
    from github import Github, RateLimitExceededException
import xml.etree.ElementTree as ET


class Issue(BaseModel):
    issue_title: str
    issue_body: str


class Issues(BaseModel):
    issues: List[Issue]


@dataclass
class CodeBlock:
    start_line: int
    end_line: int
    content: str


@dataclass
class FileModification:
    operation: Literal["replace", "insert", "delete"]
    target: Union[str, CodeBlock]
    new_content: str = None
    context_lines: int = 3
    fuzzy_match: bool = True


def _get_correct_indent_level(lines: List[str], line_index: int) -> str:
    """Determine correct indentation level by looking at surrounding structure."""
    # Look at previous line's indentation first
    if line_index > 0:
        prev_line = lines[line_index - 1].rstrip()
        if prev_line and not prev_line.endswith(","):  # Ignore continuation lines
            return prev_line[: len(prev_line) - len(prev_line.lstrip())]

    # Look backward for containing blocks
    for i in range(line_index - 1, -1, -1):
        line = lines[i].rstrip()
        if not line:  # Skip empty lines
            continue
        # Get the indentation of this line
        curr_indent = line[: len(line) - len(line.lstrip())]
        # If the line starts with 8+ spaces, it was probably properly nested
        if len(line) - len(line.lstrip()) >= 8:
            return line[: len(line) - len(line.lstrip())]
        # If we find a class or function definition, use its base indentation
        if line.lstrip().startswith(("def ", "class ", "async def ")):
            return curr_indent + "  "  # One level deeper than definition

        # If line ends with colon, use its indentation level
        if line.endswith(":"):
            return curr_indent + "  "  # One level deeper than block starter

    # Default to base level if we couldn't determine
    return ""


class github(Extensions):
    """
    The GitHub extension provides functionality to interact with GitHub repositories.
    """

    def __init__(
        self,
        GITHUB_USERNAME: str = "",
        GITHUB_API_KEY: str = "",
        **kwargs,
    ):
        self.GITHUB_USERNAME = GITHUB_USERNAME
        self.GITHUB_API_KEY = GITHUB_API_KEY
        self.commands = {
            "Clone Github Repository": self.clone_repo,
            "Get Github Repository Code Contents": self.get_repo_code_contents,
            "Get Github Repository Issues": self.get_repo_issues,
            "Get Github Repository Issue": self.get_repo_issue,
            "Get Github Assigned Issues": self.get_assigned_issues,
            "Create Github Repository": self.create_repo,
            "Create Github Repository Issue": self.create_repo_issue,
            "Update Github Repository Issue": self.update_repo_issue,
            "Get Github Repository Pull Requests": self.get_repo_pull_requests,
            "Get Github Repository Pull Request": self.get_repo_pull_request,
            "Create Github Repository Pull Request": self.create_repo_pull_request,
            "Update Github Repository Pull Request": self.update_repo_pull_request,
            "Get Github Repository Commits": self.get_repo_commits,
            "Get Github Repository Commit": self.get_repo_commit,
            "Add Comment to Github Repository Issue": self.add_comment_to_repo_issue,
            "Add Comment to Github Repository Pull Request": self.add_comment_to_repo_pull_request,
            "Close Github Issue": self.close_issue,
            "Get List of My Github Repositories": self.get_my_repos,
            "Get List of Github Repositories by Username": self.get_user_repos,
            "Upload File to Github Repository": self.upload_file_to_repo,
            "Create and Merge Github Repository Pull Request": self.create_and_merge_pull_request,
            "Improve Github Repository Codebase": self.improve_codebase,
            "Copy Github Repository Contents": self.copy_repo_contents,
            "Modify File Content on Github": self.modify_file_content,
            "Replace in File on Github": self.replace_in_file,
            "Insert in File on Github": self.insert_in_file,
            "Delete from File on Github": self.delete_from_file,
            "Fix GitHub Issue": self.fix_github_issue,
        }
        if self.GITHUB_USERNAME and self.GITHUB_API_KEY:
            try:
                self.gh = Github(self.GITHUB_API_KEY)
            except Exception as e:
                self.gh = None
        else:
            self.gh = None
        self.failures = 0
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else AGiXTSDK(
                base_uri=getenv("AGIXT_URI"),
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
            )
        )
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )
        self.activity_id = kwargs["activity_id"] if "activity_id" in kwargs else None

    def _is_python_file(self, file_path: str) -> bool:
        """
        Check if a file is a Python file based on its extension.

        Args:
            file_path (str): Path to the file

        Returns:
            bool: True if the file is a Python file, False otherwise
        """
        return file_path.endswith(".py")

    def _format_python_code(self, content: str) -> str:
        """
        Format Python code using Black.

        Args:
            content (str): Python code content to format

        Returns:
            str: Formatted Python code
        """
        try:
            mode = black.Mode(
                target_versions={black.TargetVersion.PY37},
                line_length=88,
                string_normalization=True,
                is_pyi=False,
            )
            formatted_content = black.format_str(content, mode=mode)
            return formatted_content
        except Exception as e:
            logging.warning(f"Failed to format Python code with Black: {str(e)}")
            return content

    # Improvement 1: Enhance the _normalize_code function to better handle indentation
    def _normalize_code(
        self, code: str, preserve_indent: bool = False, indent_sensitive: bool = True
    ) -> str:
        """Normalize code for comparison while handling indentation carefully.

        Args:
            code: The code to normalize
            preserve_indent: Whether to preserve indentation in output
            indent_sensitive: Whether to treat the code as indent-sensitive (Python, YAML)

        Returns:
            Normalized code string
        """
        if not code:
            return code

        lines = code.splitlines()

        # Remove empty lines at start and end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        if not lines:
            return ""

        # Get base indentation from first non-empty line
        first_line = next((line for line in lines if line.strip()), "")
        base_indent = len(first_line) - len(first_line.lstrip())

        normalized = []
        for line in lines:
            if not line.strip():
                normalized.append("")
                continue

            if preserve_indent:
                # Calculate relative indentation
                current_indent = len(line) - len(line.lstrip())
                relative_indent = max(0, current_indent - base_indent)
                content = line.lstrip()
                normalized_line = " " * relative_indent + content
            else:
                normalized_line = line.lstrip()

            # Normalize Python-specific syntax
            normalized_line = re.sub(
                r"\s*=\s*", "=", normalized_line
            )  # Normalize around =
            normalized_line = re.sub(
                r"\s*,\s*", ",", normalized_line
            )  # Normalize around ,

            # Preserve indentation level structure for indent-sensitive languages
            if indent_sensitive and not preserve_indent:
                # Add a marker for indentation level (not the actual spaces)
                indentation_level = (
                    len(line) - len(line.lstrip())
                ) // 4  # Assuming 4 spaces per indent
                normalized_line = f"IL{indentation_level}:{normalized_line}"
            else:
                normalized_line = re.sub(
                    r"\s+", " ", normalized_line
                )  # Normalize other whitespace

            normalized.append(normalized_line)

        return "\n".join(normalized)

    # Improvement 2: Update the _find_pattern_boundaries method to use improved indentation handling
    def _find_pattern_boundaries(
        self,
        file_lines: List[str],
        target: str,
        fuzzy_match: bool = True,
        operation: str = None,
    ) -> tuple[int, int, int]:
        """Find start and end line indices of the target code block in file lines.

        Args:
            file_lines: List of lines from the file
            target: The target code block to find
            fuzzy_match: Whether to allow fuzzy matching
            operation: The type of operation being performed

        Returns:
            Tuple of (start_line, end_line, indent_level)
        """
        # Handle special cases for empty files or new files
        if not file_lines:
            if operation == "insert":
                return 0, 0, 0
            raise ValueError("Cannot find pattern in empty file")

        # Handle numeric line number targets
        if str(target).isdigit():
            line_num = int(target)
            if line_num <= len(file_lines):
                return (
                    line_num,
                    line_num,
                    (
                        len(file_lines[line_num - 1])
                        - len(file_lines[line_num - 1].lstrip())
                        if line_num > 0
                        else 0
                    ),
                )
            elif operation == "insert":
                # Allow insertion at end of file
                return len(file_lines), len(file_lines), 0
            else:
                raise ValueError(
                    f"Line number {line_num} exceeds file length {len(file_lines)}"
                )

        # Split and clean target
        target_lines = [line.rstrip() for line in target.splitlines()]
        while target_lines and not target_lines[0].strip():
            target_lines.pop(0)
        while target_lines and not target_lines[-1].strip():
            target_lines.pop()

        if not target_lines:
            raise ValueError("Empty target after cleaning")

        # Get target base indentation
        target_base_indent = len(target_lines[0]) - len(target_lines[0].lstrip())

        # Detect if this is an indent-sensitive language based on file extension or content
        is_indent_sensitive = self._is_indent_sensitive_content(target_lines)

        # Special handling for insertions
        if operation == "insert":
            if re.match(
                r"^(\s*)(@.*\n)?(async\s+)?(?:def|class)\s+\w+", target_lines[0]
            ):
                return self._handle_insertion_point(
                    file_lines, target_lines[0].lstrip()
                )
            # If it's an insert operation and we can't find the target,
            # suggest inserting at the end of the file
            if len(file_lines) > 0:
                last_line_indent = len(file_lines[-1]) - len(file_lines[-1].lstrip())
                return len(file_lines), len(file_lines), last_line_indent // 4

        # Try different indentation variations of the target
        target_variations = self._try_different_indentations(target)
        best_matches = []

        # Process file lines
        processed_file_lines = [line.rstrip() for line in file_lines]
        window_size = len(target_lines)

        # For very small targets (1-2 lines), try to match on structure and content
        if len(target_lines) <= 2 and is_indent_sensitive:
            return self._find_small_target_match(
                processed_file_lines, target_lines, fuzzy_match, operation
            )

        # Look for matches with each target variation
        for target_var in target_variations:
            target_var_lines = target_var.splitlines()

            for i in range(len(processed_file_lines) - window_size + 1):
                window_lines = processed_file_lines[i : i + window_size]
                window_text = "\n".join(window_lines)

                # Compare normalized versions with appropriate indent sensitivity
                window_normalized = self._normalize_code(
                    window_text, False, is_indent_sensitive
                )
                target_normalized = self._normalize_code(
                    target_var, False, is_indent_sensitive
                )

                similarity = difflib.SequenceMatcher(
                    None, window_normalized, target_normalized
                ).ratio()

                # Adjust similarity based on indentation structure match
                if is_indent_sensitive:
                    indent_similarity = self._compare_indent_structure(
                        window_lines, target_var_lines
                    )
                    # Weight both content similarity and indentation structure
                    adjusted_similarity = (similarity * 0.7) + (indent_similarity * 0.3)
                else:
                    adjusted_similarity = similarity

                if adjusted_similarity > 0:
                    # Get window indentation
                    window_base_indent = len(window_lines[0]) - len(
                        window_lines[0].lstrip()
                    )

                    best_matches.append(
                        {
                            "start_line": i,
                            "score": adjusted_similarity,
                            "segment": window_lines,
                            "indent": window_base_indent,
                            "target_var": target_var,
                        }
                    )

        if not best_matches:
            # Try more aggressive normalization if no matches found
            return self._find_pattern_with_aggressive_normalization(
                file_lines, target, fuzzy_match, operation, is_indent_sensitive
            )

        # Sort by score and indentation similarity
        best_matches.sort(
            key=lambda x: (x["score"], -abs(x["indent"] - target_base_indent)),
            reverse=True,
        )

        best_match = best_matches[0]

        # Adjust thresholds based on indent sensitivity and fuzzy matching
        if is_indent_sensitive:
            threshold = 0.8 if fuzzy_match else 0.9
        else:
            threshold = 0.7 if fuzzy_match else 0.85

        if best_match["score"] < threshold:
            # For insert operations, if we can't find a good match,
            # suggest inserting at the end of the file
            if operation == "insert":
                last_line_indent = len(file_lines[-1]) - len(file_lines[-1].lstrip())
                return len(file_lines), len(file_lines), last_line_indent // 4

            # Try one more time with aggressive normalization
            try:
                return self._find_pattern_with_aggressive_normalization(
                    file_lines, target, fuzzy_match, operation, is_indent_sensitive
                )
            except ValueError:
                error_msg = [
                    f"Best match score ({best_match['score']:.2f}) below threshold ({threshold}).",
                    "",
                    "Target:",
                    target,
                    "",
                    "Best matching segment found:",
                    "\n".join(best_match["segment"]),
                    "",
                    "Please provide a more accurate target.",
                ]
                raise ValueError("\n".join(error_msg))

        return (
            best_match["start_line"],
            best_match["start_line"] + len(target_lines),
            best_match["indent"] // 4,
        )

    # Improvement 3: Add methods to better handle indentation structure
    def _is_indent_sensitive_content(self, code_lines: List[str]) -> bool:
        """Detect if content is likely to be indentation-sensitive (Python, YAML).

        Args:
            code_lines: List of code lines to analyze

        Returns:
            bool: True if content appears to be indentation-sensitive
        """
        # Check for typical Python patterns
        python_patterns = [
            r"^\s*def\s+\w+\(.*\):",
            r"^\s*class\s+\w+(\(.*\))?:",
            r"^\s*if\s+.*:",
            r"^\s*for\s+.*:",
            r"^\s*while\s+.*:",
            r"^\s*try:",
            r"^\s*except.*:",
        ]

        # Check for YAML patterns
        yaml_patterns = [
            r"^\s*\w+:",
            r"^\s*-\s+\w+:",
        ]

        # Count matches for each type
        python_matches = 0
        yaml_matches = 0

        for line in code_lines:
            for pattern in python_patterns:
                if re.match(pattern, line):
                    python_matches += 1
                    break

            for pattern in yaml_patterns:
                if re.match(pattern, line):
                    yaml_matches += 1
                    break

        # If we have good signal for either type, consider it indent-sensitive
        return python_matches > 0 or yaml_matches > 2

    def _compare_indent_structure(
        self, window_lines: List[str], target_lines: List[str]
    ) -> float:
        """Compare the indentation structure of two code blocks.

        Args:
            window_lines: Lines from the file being searched
            target_lines: Lines from the target code block

        Returns:
            float: Similarity score (0-1) based on indentation structure
        """
        if len(window_lines) != len(target_lines):
            return 0.0

        # Extract indentation levels
        window_indents = [len(line) - len(line.lstrip()) for line in window_lines]
        target_indents = [len(line) - len(line.lstrip()) for line in target_lines]

        # Normalize indentation levels relative to first line
        if window_indents and target_indents:
            window_base = window_indents[0]
            target_base = target_indents[0]

            window_relative = [
                max(0, indent - window_base) for indent in window_indents
            ]
            target_relative = [
                max(0, indent - target_base) for indent in target_indents
            ]

            # Convert to indentation "shape" - just care about when indentation changes
            window_shape = [0]
            target_shape = [0]

            for i in range(1, len(window_relative)):
                # Only care about the direction of change, not the magnitude
                if window_relative[i] > window_relative[i - 1]:
                    window_shape.append(1)  # Indent increased
                elif window_relative[i] < window_relative[i - 1]:
                    window_shape.append(-1)  # Indent decreased
                else:
                    window_shape.append(0)  # No change

            for i in range(1, len(target_relative)):
                if target_relative[i] > target_relative[i - 1]:
                    target_shape.append(1)
                elif target_relative[i] < target_relative[i - 1]:
                    target_shape.append(-1)
                else:
                    target_shape.append(0)

            # Compare the shapes
            matches = sum(1 for w, t in zip(window_shape, target_shape) if w == t)
            return matches / len(window_shape)

        return 0.0

    def _find_small_target_match(
        self,
        file_lines: List[str],
        target_lines: List[str],
        fuzzy_match: bool = True,
        operation: str = None,
    ) -> tuple[int, int, int]:
        """Find match for small targets (1-2 lines) focusing on structure and content.

        For small targets, we need to be more careful as they could match in many places.
        This method uses both content and surrounding structure.

        Args:
            file_lines: List of lines from the file
            target_lines: List of target lines to find
            fuzzy_match: Whether to allow fuzzy matching
            operation: The operation being performed

        Returns:
            Tuple of (start_line, end_line, indent_level)
        """
        # For single line targets, check key tokens and structure
        target_first_line = target_lines[0].lstrip()

        # Extract key tokens (function names, class names, etc.)
        key_token_match = re.search(r"(def|class)\s+(\w+)", target_first_line)
        if key_token_match:
            token_type, token_name = key_token_match.groups()

            # Look for matches with the same key token
            for i, line in enumerate(file_lines):
                line_stripped = line.lstrip()
                if re.search(f"{token_type}\\s+{token_name}", line_stripped):
                    # Found a potential match for a function or class definition
                    indent_level = len(line) - len(line_stripped)
                    return i, i + len(target_lines), indent_level // 4

        # If no key token match or multiple lines, fallback to token-based matching
        target_tokens = set()
        for line in target_lines:
            # Extract significant tokens (identifiers, keywords)
            tokens = re.findall(r"\b\w+\b", line)
            target_tokens.update(
                [t for t in tokens if len(t) > 2]
            )  # Only tokens longer than 2 chars

        best_matches = []
        # Scan through file looking for concentrations of target tokens
        for i in range(len(file_lines) - len(target_lines) + 1):
            window_lines = file_lines[i : i + len(target_lines)]
            window_tokens = set()

            for line in window_lines:
                tokens = re.findall(r"\b\w+\b", line)
                window_tokens.update([t for t in tokens if len(t) > 2])

            # Calculate token overlap
            common_tokens = target_tokens.intersection(window_tokens)
            if not common_tokens:
                continue

            token_similarity = (
                len(common_tokens) / len(target_tokens) if target_tokens else 0
            )

            # Also consider direct string similarity
            string_similarity = difflib.SequenceMatcher(
                None,
                "\n".join(line.lstrip() for line in target_lines),
                "\n".join(line.lstrip() for line in window_lines),
            ).ratio()

            # Combined score
            score = (token_similarity * 0.7) + (string_similarity * 0.3)

            if score > 0.5:  # Only consider reasonably good matches
                indent_level = len(window_lines[0]) - len(window_lines[0].lstrip())
                best_matches.append(
                    {
                        "start_line": i,
                        "score": score,
                        "segment": window_lines,
                        "indent": indent_level,
                    }
                )

        if not best_matches:
            if operation == "insert":
                last_line_indent = len(file_lines[-1]) - len(file_lines[-1].lstrip())
                return len(file_lines), len(file_lines), last_line_indent // 4
            raise ValueError(f"Could not find a match for the target: {target_lines}")

        # Sort matches by score
        best_matches.sort(key=lambda x: x["score"], reverse=True)
        best_match = best_matches[0]

        # Higher threshold for small targets to avoid false positives
        threshold = 0.6 if fuzzy_match else 0.75

        if best_match["score"] < threshold:
            if operation == "insert":
                last_line_indent = len(file_lines[-1]) - len(file_lines[-1].lstrip())
                return len(file_lines), len(file_lines), last_line_indent // 4
            raise ValueError(
                f"Best match score ({best_match['score']:.2f}) below threshold ({threshold})"
            )

        return (
            best_match["start_line"],
            best_match["start_line"] + len(target_lines),
            best_match["indent"] // 4,
        )

    # Improvement 4: Update the aggressive normalization method to be indent-aware
    def _find_pattern_with_aggressive_normalization(
        self,
        file_lines: List[str],
        target: str,
        fuzzy_match: bool = True,
        operation: str = None,
        indent_sensitive: bool = False,
    ) -> tuple[int, int, int]:
        """Attempt to find pattern with more aggressive normalization.

        This is a fallback method that tries harder to find matches by:
        1. Removing all whitespace except for indentation structure
        2. Normalizing variable names
        3. Ignoring comments

        Args:
            file_lines: List of lines from the file
            target: The target code block to find
            fuzzy_match: Whether to allow fuzzy matching
            operation: The type of operation being performed
            indent_sensitive: Whether to preserve indentation structure

        Returns:
            Tuple of (start_line, end_line, indent_level)
        """

        def aggressive_normalize(
            code: str, preserve_indent_structure: bool = False
        ) -> str:
            lines = code.splitlines()
            result = []

            for line in lines:
                # Skip comments
                if line.lstrip().startswith("#"):
                    continue

                # Remove inline comments
                line = re.sub(r"#.*$", "", line)

                if preserve_indent_structure:
                    # Preserve indentation level but not the actual spaces
                    indent_level = len(line) - len(line.lstrip())
                    content = line.lstrip()

                    # Skip empty lines
                    if not content:
                        continue

                    # Normalize variable names and collapse spaces
                    content = re.sub(r"[a-zA-Z_]\w*", "VAR", content)
                    content = re.sub(r"\s+", "", content)

                    # Add indent marker
                    result.append(f"I{indent_level}:{content}")
                else:
                    # Just fully normalize without preserving structure
                    line = line.strip()
                    if not line:
                        continue
                    line = re.sub(r"[a-zA-Z_]\w*", "VAR", line)
                    line = re.sub(r"\s+", "", line)
                    result.append(line)

            return "\n".join(result)

        target_lines = target.splitlines()
        window_size = len(target_lines)

        # Skip empty lines in target
        target_lines = [line for line in target_lines if line.strip()]
        if not target_lines:
            raise ValueError("Empty target after cleaning")

        # Aggressively normalize target
        target_normalized = aggressive_normalize(target, indent_sensitive)

        best_matches = []

        # Create windows of appropriate size for comparison
        filtered_file_lines = [line for line in file_lines if line.strip()]

        # Use dynamic window size since we've removed empty lines
        min_window_size = len(target_lines)
        max_window_size = min(len(filtered_file_lines), min_window_size * 2)

        for window_size in range(min_window_size, max_window_size + 1):
            for i in range(len(file_lines) - window_size + 1):
                window = "\n".join(file_lines[i : i + window_size])

                # Skip windows with too little content
                if not window.strip():
                    continue

                window_normalized = aggressive_normalize(window, indent_sensitive)

                # Skip if normalized window is empty
                if not window_normalized:
                    continue

                similarity = difflib.SequenceMatcher(
                    None, window_normalized, target_normalized
                ).ratio()

                if similarity > 0:
                    indent = len(file_lines[i]) - len(file_lines[i].lstrip())

                    # For indent-sensitive code, check indentation patterns too
                    if indent_sensitive:
                        # Extract non-empty lines for indentation structure comparison
                        window_lines = [
                            line
                            for line in file_lines[i : i + window_size]
                            if line.strip()
                        ]
                        target_lines_clean = [
                            line for line in target_lines if line.strip()
                        ]

                        # Compare indentation structure
                        indent_similarity = self._compare_indent_structure(
                            window_lines, target_lines_clean
                        )

                        # Adjust similarity score
                        adjusted_similarity = (similarity * 0.6) + (
                            indent_similarity * 0.4
                        )
                    else:
                        adjusted_similarity = similarity

                    best_matches.append(
                        {
                            "start_line": i,
                            "score": adjusted_similarity,
                            "segment": file_lines[i : i + window_size],
                            "indent": indent,
                        }
                    )

        if not best_matches:
            if operation == "insert":
                # For inserts, default to end of file
                last_line_indent = (
                    len(file_lines[-1]) - len(file_lines[-1].lstrip())
                    if file_lines
                    else 0
                )
                return len(file_lines), len(file_lines), last_line_indent // 4

            raise ValueError("No matches found even with aggressive normalization")

        best_matches.sort(key=lambda x: x["score"], reverse=True)
        best_match = best_matches[0]

        # Adjust thresholds based on operation and sensitivity
        if indent_sensitive:
            threshold = 0.55 if fuzzy_match else 0.65
        else:
            threshold = 0.5 if fuzzy_match else 0.6

        if operation == "insert":
            # Lower threshold for inserts
            threshold = max(0.4, threshold - 0.1)

        if best_match["score"] < threshold:
            if operation == "insert":
                # For inserts, default to end of file
                last_line_indent = (
                    len(file_lines[-1]) - len(file_lines[-1].lstrip())
                    if file_lines
                    else 0
                )
                return len(file_lines), len(file_lines), last_line_indent // 4

            raise ValueError(
                f"Best aggressive match score ({best_match['score']:.2f}) below threshold ({threshold})"
            )

        # Determine end line more carefully for indent-sensitive code
        if indent_sensitive:
            # Find where the indentation level returns to the starting level or less
            start_line = best_match["start_line"]
            start_indent = len(file_lines[start_line]) - len(
                file_lines[start_line].lstrip()
            )

            end_line = start_line + 1
            while end_line < len(file_lines) and end_line < start_line + window_size:
                line = file_lines[end_line]
                if line.strip() and len(line) - len(line.lstrip()) <= start_indent:
                    break
                end_line += 1

            return start_line, end_line, start_indent // 4
        else:
            # Use fixed window size for non-indent-sensitive code
            return (
                best_match["start_line"],
                best_match["start_line"] + len(target_lines),
                best_match["indent"] // 4,
            )

    # Improvement 5: Update _indent_code_block to handle indentation more intelligently
    def _indent_code_block(self, content: str, base_indent: str) -> List[str]:
        """Apply base indentation to a block of code while preserving relative indents.

        Args:
            content: The content to indent
            base_indent: Base indentation to apply (as a string of spaces)

        Returns:
            List of indented lines
        """
        lines = content.splitlines()
        if not lines:
            return []

        # Find any existing indentation in the content
        indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
        min_indent = min(indents) if indents else 0

        # Check if this is Python/YAML style indentation
        is_indent_sensitive = self._is_indent_sensitive_content(lines)
        uses_tabs = any("\t" in line for line in lines)

        # Determine appropriate indent character (space or tab)
        indent_char = "\t" if uses_tabs else " "
        spaces_per_level = 1 if uses_tabs else 4  # Default to 4 spaces per level

        # Try to infer spaces per level from the content
        indent_differences = []
        for i in range(1, len(indents)):
            diff = abs(indents[i] - indents[i - 1])
            if diff > 0:
                indent_differences.append(diff)

        if indent_differences:
            # Find the most common difference that's at least 2
            common_diffs = [diff for diff in indent_differences if diff >= 2]
            if common_diffs:
                spaces_per_level = min(common_diffs)

        result = []

        # Detect if content is from a code block that has incorrect base indentation
        first_non_empty = next((i for i, line in enumerate(lines) if line.strip()), 0)
        first_line_indent = len(lines[first_non_empty]) - len(
            lines[first_non_empty].lstrip()
        )

        # Look for common indentation patterns in code
        for i, line in enumerate(lines):
            if not line.strip():
                # Preserve empty lines
                result.append("\n")
                continue

            # Calculate relative indentation from the original content
            current_indent = len(line) - len(line.lstrip())

            if is_indent_sensitive:
                # For Python/YAML, preserve relative indentation carefully
                relative_level = (current_indent - min_indent) // spaces_per_level
                indent_string = (
                    base_indent + (indent_char * spaces_per_level) * relative_level
                )
                result.append(f"{indent_string}{line.lstrip()}\n")
            else:
                # For other languages, focus on preserving the first line indent
                if i == first_non_empty:
                    result.append(f"{base_indent}{line.lstrip()}\n")
                else:
                    # Calculate indentation relative to the first line
                    relative_indent = current_indent - first_line_indent
                    if relative_indent > 0:
                        # Apply base indent plus relative indent
                        result.append(
                            f"{base_indent}{' ' * relative_indent}{line.lstrip()}\n"
                        )
                    else:
                        # Same level as first line
                        result.append(f"{base_indent}{line.lstrip()}\n")

        return result

    def _is_js_or_ts_file(self, file_path: str) -> bool:
        """
        Check if a file is a JavaScript or TypeScript file based on its extension.

        Args:
            file_path (str): Path to the file

        Returns:
            bool: True if the file is a JS/TS file, False otherwise
        """
        return file_path.endswith((".js", ".jsx", ".ts", ".tsx"))

    def _format_js_ts_code(self, content: str) -> str:
        """
        Format JavaScript or TypeScript code using Prettier.

        Args:
            content (str): JS/TS code content to format

        Returns:
            str: Formatted JS/TS code
        """
        try:
            import subprocess
            import tempfile
            import os

            # Create a temporary file to store the code
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", delete=False
            ) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            try:
                # Try to use local prettier installation first
                result = subprocess.run(
                    ["npx", "prettier", "--write", temp_file_path],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                # If local prettier fails, install it globally and retry
                try:
                    subprocess.run(["npm", "install", "-g", "prettier"], check=True)
                    result = subprocess.run(
                        ["prettier", "--write", temp_file_path],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                except subprocess.CalledProcessError as e:
                    logging.warning(
                        f"Failed to format JS/TS code with Prettier: {str(e)}"
                    )
                    return content

            # Read the formatted content
            with open(temp_file_path, "r") as temp_file:
                formatted_content = temp_file.read()

            # Clean up temporary file
            os.unlink(temp_file_path)

            return formatted_content
        except Exception as e:
            logging.warning(f"Failed to format JS/TS code with Prettier: {str(e)}")
            return content

    async def clone_repo(self, repo_url: str) -> str:
        """
        Clone a GitHub repository to the local workspace

        Args:
        repo_url (str): The URL of the GitHub repository to clone

        Returns:
        str: The result of the cloning operation
        """
        split_url = repo_url.split("//")
        if self.GITHUB_USERNAME is not None and self.GITHUB_API_KEY is not None:
            auth_repo_url = f"//{self.GITHUB_USERNAME}:{self.GITHUB_API_KEY}@".join(
                split_url
            )
        else:
            auth_repo_url = "//".join(split_url)
        try:
            repo_name = repo_url.split("/")[-1]
            repo_dir = os.path.join(self.WORKING_DIRECTORY, repo_name)
            if os.path.exists(repo_dir):
                # Pull the latest changes
                repo = git.Repo(repo_dir)
                repo.remotes.origin.pull()
                self.failures = 0
                return f"Pulled latest changes for {repo_url} to {repo_dir}"
            else:
                git.Repo.clone_from(
                    url=auth_repo_url,
                    to_path=repo_dir,
                )
            self.failures = 0
            return f"Cloned {repo_url} to {repo_dir}"
        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.clone_repo(repo_url)
            return f"Error: {str(e)}"

    async def create_repo(
        self, repo_name: str, content_of_readme: str, org: str = None
    ) -> str:
        """
        Create a new private GitHub repository

        Args:
        repo_name (str): The name of the repository to create
        content_of_readme (str): The content of the README.md file

        Returns:
        str: The URL of the newly created repository
        """
        try:
            if not org:
                try:
                    user = self.gh.get_organization(self.GITHUB_USERNAME)
                except:
                    user = self.gh.get_user(self.GITHUB_USERNAME)
            else:
                user = self.gh.get_organization(org)
            repo = user.create_repo(repo_name, private=True)
            repo_url = repo.clone_url
            repo_dir = os.path.join(self.WORKING_DIRECTORY, repo_name)
            repo = git.Repo.init(repo_dir)
            with open(f"{repo_dir}/README.md", "w") as f:
                f.write(content_of_readme)
            repo.git.add(A=True)
            repo.git.commit(m="Added README")
            repo.create_remote("origin", repo_url)
            repo.git.push("origin", "HEAD:main")
            self.failures = 0
            return repo_url
        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.create_repo(repo_name, content_of_readme)
            return f"Error: {str(e)}"

    async def get_repo_code_contents(self, repo_url: str) -> str:
        """
        Get the code contents of a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository

        Returns:
        str: The code contents of the repository in markdown format
        """
        branch = None
        if "/tree/" in repo_url:
            # Extract branch name and clean up repo URL
            base_url, branch_path = repo_url.split("/tree/", 1)
            branch = branch_path.split("/")[0]
            repo_url = base_url
            repo_name = repo_url.split("/")[-1]
        else:
            repo_name = repo_url.split("/")[-1]

        # Clone the repository (with branch if specified)
        clone_result = await self.clone_repo(repo_url)
        if "Error:" in clone_result:
            return f"Error cloning repository: {clone_result}"

        # If a branch was specified, checkout that branch
        if branch:
            repo_dir = os.path.join(self.WORKING_DIRECTORY, repo_name)
            try:
                repo = git.Repo(repo_dir)
                repo.git.checkout(branch)
            except Exception as e:
                return f"Error checking out branch {branch}: {str(e)}"

        output_file = os.path.join(self.WORKING_DIRECTORY, f"{repo_name}.md")
        python_files = []
        other_files = []
        powershell_files = []
        js_files = []
        ts_files = []
        kt_files = []
        lua_files = []
        xml_files = []
        md_files = []
        json_files = []
        gql_files = []
        sh_files = []

        for root, dirs, files in os.walk(
            os.path.join(self.WORKING_DIRECTORY, repo_name)
        ):
            for file in files:
                if "node_modules" in root or "node_modules" in file:
                    continue
                if "package-lock.json" in file:
                    continue
                if ".stories." in file:
                    continue
                if "default_agent.json" in file:
                    continue
                if ".env" in file:
                    continue
                if file.endswith(".py"):
                    python_files.append(os.path.join(root, file))
                elif file.endswith(".ps1"):
                    powershell_files.append(os.path.join(root, file))
                elif file in [
                    "Dockerfile",
                    "requirements.txt",
                    "static-requirements.txt",
                ] or file.endswith(".yml"):
                    other_files.append(os.path.join(root, file))
                elif file.endswith(".js") or file.endswith(".jsx"):
                    js_files.append(os.path.join(root, file))
                elif file.endswith(".ts") or file.endswith(".tsx"):
                    ts_files.append(os.path.join(root, file))
                elif file.endswith(".kt") or file.endswith(".java"):
                    kt_files.append(os.path.join(root, file))
                elif file.endswith(".lua"):
                    lua_files.append(os.path.join(root, file))
                elif file.endswith(".xml"):
                    # if path is app/src/main/res/layout, then we will add the xml files, but not other folders.
                    if "layout" in root.split(os.path.sep):
                        xml_files.append(os.path.join(root, file))
                elif file.endswith(".md"):
                    md_files.append(os.path.join(root, file))
                elif file.endswith(".json"):
                    json_files.append(os.path.join(root, file))
                elif file.endswith(".gql"):
                    gql_files.append(os.path.join(root, file))
                elif file.endswith(".sh"):
                    sh_files.append(os.path.join(root, file))

        if os.path.exists(output_file):
            os.remove(output_file)

        with open(output_file, "w", encoding="utf-8") as markdown_file:
            for file_paths, file_type in [
                (other_files, "yaml"),
                (powershell_files, "powershell"),
                (python_files, "python"),
                (js_files, "javascript"),
                (ts_files, "typescript"),
                (kt_files, "kotlin"),
                (lua_files, "lua"),
                (xml_files, "xml"),
                (md_files, "markdown"),
                (json_files, "json"),
                (gql_files, "graphql"),
                (sh_files, "shell"),
            ]:
                for file_path in file_paths:
                    # Make sure the file isn't output.md
                    if output_file in file_path:
                        continue
                    markdown_file.write(f"**{file_path}**\n")
                    with open(file_path, "r", encoding="utf-8") as code_file:
                        content = code_file.read()
                        markdown_file.write(f"```{file_type}\n{content}\n```\n\n")
        with open(output_file, "r", encoding="utf-8") as markdown_file:
            content = markdown_file.read()

        content = content.replace("<|endoftext|>", "")
        return content

    async def get_repo_issues(self, repo_url: str) -> str:
        """
        Get the open issues for a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository

        Returns:
        str: The open issues for the repository
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issues = repo.get_issues(state="open")
            issue_list = []
            for issue in issues:
                issue_list.append(f"#{issue.number}: {issue.title}")
            self.failures = 0
            return f"Open Issues for GitHub Repository at {repo_url}:\n\n" + "\n".join(
                issue_list
            )
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_repo_issues(repo_url)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_repo_issue(self, repo_url: str, issue_number: int) -> str:
        """
        Get the details of a specific issue in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        issue_number (int): The issue number to retrieve

        Returns:
        str: The details of the issue
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            try:
                issue = repo.get_issue(
                    int(issue_number)
                )  # Ensure issue_number is cast to int
                self.failures = 0
                return f"Issue Details for GitHub Repository at {repo_url}\n\n{issue.number}: {issue.title}\n\n{issue.body}"
            except ValueError as e:
                return f"Error: Invalid issue number format - {str(e)}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_repo_issue(repo_url, issue_number)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def create_repo_issue(
        self, repo_url: str, title: str, body: str, assignee: str = None
    ) -> str:
        """
        Create a new issue in a GitHub repository with an optional assignee

        Args:
        repo_url (str): The URL of the GitHub repository
        title (str): The title of the issue
        body (str): The body of the issue
        assignee (str): The assignee for the issue

        Returns:
        str: The result of the issue creation operation and branch creation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            try:
                issue = repo.create_issue(title=title, body=body, assignee=assignee)
            except Exception as e:
                issue = repo.create_issue(title=title, body=body)
            self.failures = 0
            return f"Created new issue in GitHub Repository at {repo_url}\n\n{issue.number}: {issue.title}\n\n{issue.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.create_repo_issue(
                    repo_url=repo_url, title=title, body=body, assignee=assignee
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def update_repo_issue(
        self,
        repo_url: str,
        issue_number: int,
        title: str,
        body: str,
        assignee: str = None,
    ) -> str:
        """
        Update an existing issue in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        issue_number (int): The issue number to update
        title (str): The new title of the issue
        body (str): The new body of the issue
        assignee (str): The new assignee for the issue

        Returns:
        str: The result of the issue update operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.get_issue(issue_number)
            issue.edit(title=title, body=body, assignee=assignee)
            self.failures = 0
            return f"Updated issue in GitHub Repository at {repo_url}\n\n{issue.number}: {issue.title}\n\n{issue.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.update_repo_issue(repo_url, issue_number, title, body)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_repo_pull_requests(self, repo_url: str) -> str:
        """
        Get the open pull requests for a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository

        Returns:
        str: The open pull requests for the repository
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_requests = repo.get_pulls(state="open")
            pr_list = []
            for pr in pull_requests:
                pr_list.append(f"#{pr.number}: {pr.title}")
            self.failures = 0
            return (
                f"Open Pull Requests for GitHub Repository at {repo_url}:\n\n"
                + "\n".join(pr_list)
            )
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_repo_pull_requests(repo_url)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_repo_pull_request(
        self, repo_url: str, pull_request_number: int
    ) -> str:
        """
        Get the details of a specific pull request in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        pull_request_number (int): The pull request number to retrieve

        Returns:
        str: The details of the pull request
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.get_pull(pull_request_number)
            self.failures = 0
            return f"Pull Request Details for GitHub Repository at {repo_url}\n\n#{pull_request.number}: {pull_request.title}\n\n{pull_request.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_repo_pull_request(repo_url, pull_request_number)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def create_repo_pull_request(
        self, repo_url: str, title: str, body: str, head: str, base: str
    ) -> str:
        """
        Create a new pull request in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        title (str): The title of the pull request
        body (str): The body of the pull request
        head (str): The branch to merge from
        base (str): The branch to merge to

        Returns:
        str: The result of the pull request creation operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.create_pull(
                title=title, body=body, head=head, base=base
            )
            self.failures = 0
            return f"Created new pull request #{pull_request.number} `{pull_request.title}`."
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.create_repo_pull_request(
                    repo_url, title, body, head, base
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def update_repo_pull_request(
        self, repo_url: str, pull_request_number: int, title: str, body: str
    ) -> str:
        """
        Update an existing pull request in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        pull_request_number (int): The pull request number to update
        title (str): The new title of the pull request
        body (str): The new body of the pull request

        Returns:
        str: The result of the pull request update operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.get_pull(pull_request_number)
            pull_request.edit(title=title, body=body)
            self.failures = 0
            return f"Updated pull request in GitHub Repository at {repo_url}\n\n#{pull_request.number}: {pull_request.title}\n\n{pull_request.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.update_repo_pull_request(
                    repo_url, pull_request_number, title, body
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_repo_commits(self, repo_url: str, days: int = 7) -> str:
        """
        Get the commits for a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        days (int): The number of days to retrieve commits for (default is 7 days)

        Returns:
        str: The commits for the repository
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            if days == 0:
                commits = repo.get_commits()
            else:
                since = datetime.datetime.now() - datetime.timedelta(days=days)
                commits = repo.get_commits(since=since)
            commit_list = []
            for commit in commits:
                commit_list.append(f"{commit.sha}: {commit.commit.message}")
            self.failures = 0
            return (
                f"Commits for GitHub Repository at {repo_url} (last {days} days):\n\n"
                + "\n".join(commit_list)
            )
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_repo_commits(repo_url, days)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_repo_commit(self, repo_url: str, commit_sha: str) -> str:
        """
        Get the details of a specific commit in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        commit_sha (str): The commit SHA to retrieve

        Returns:
        str: The details of the commit
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            commit = repo.get_commit(commit_sha)
            self.failures = 0
            return f"Commit Details for GitHub Repository at {repo_url}\n\n{commit.sha}: {commit.commit.message}\n\n{commit.commit.author.name} ({commit.commit.author.email})\n\n{commit.files}"
        except RateLimitExceededException:
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def add_comment_to_repo_issue(
        self,
        repo_url: str,
        issue_number: int,
        comment_body: str,
        close_issue: bool = False,
    ) -> str:
        """
        Add a comment to an issue in a GitHub repository and optionally close the issue

        Args:
        repo_url (str): The URL of the GitHub repository
        issue_number (int): The issue number to add a comment to
        comment_body (str): The body of the comment
        close_issue (bool): Whether to close the issue after adding the comment (default: False)

        Returns:
        str: The result of the comment addition operation and issue closure if applicable
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.get_issue(issue_number)
            comment = issue.create_comment(comment_body)

            result = f"Added comment to issue #{issue.number} in GitHub Repository at {repo_url}\n\n{comment.body}"

            if close_issue:
                issue.edit(state="closed")
                result += f"\n\nIssue #{issue.number} has been closed."

            self.failures = 0
            return result
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.add_comment_to_repo_issue(
                    repo_url, issue_number, comment_body, close_issue
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def add_comment_to_repo_pull_request(
        self, repo_url: str, pull_request_number: int, comment_body: str
    ) -> str:
        """
        Add a comment to a pull request in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        pull_request_number (int): The pull request number to add a comment to
        comment_body (str): The body of the comment

        Returns:
        str: The result of the comment addition operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.get_pull(pull_request_number)
            comment = pull_request.create_issue_comment(comment_body)
            self.failures = 0
            return f"Added comment to pull request #{pull_request.number} in GitHub Repository at {repo_url}\n\n{comment.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.add_comment_to_repo_pull_request(
                    repo_url, pull_request_number, comment_body
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def close_issue(self, repo_url, issue_number):
        """
        Close an issue in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        issue_number (int): The issue number to close

        Returns:
        str: The result of the issue closure operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.get_issue(issue_number)

            # Close the ticket
            issue.edit(state="closed")

            self.failures = 0
            return (
                f"Closed ticket in GitHub Repository: {repo_url}, Issue #{issue_number}"
            )
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.close_ticket(repo_url, issue_number)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_my_repos(self) -> str:
        """
        Get all repositories that the token is associated with the owner owning or collaborating on repositories.

        Returns:
        str: Repository list separated by new lines.
        """
        try:
            all_repos = []
            page = 1
            while True:
                response = requests.get(
                    f"https://api.github.com/user/repos?type=all&page={page}",
                    headers={
                        "Authorization": f"token {self.GITHUB_API_KEY}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                repos = response.json()
                if not repos:
                    break
                all_repos.extend(repos)
                page += 1
            repo_list = []
            for repo in all_repos:
                repo_name = repo["full_name"]
                if not repo["archived"]:
                    repo_list.append(repo_name)
            self.failures = 0
            return f"### Accessible Github Repositories\n\n" + "\n".join(repo_list)
        except requests.exceptions.RequestException as e:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_my_repos()
            return f"Error: {str(e)}"

    async def get_user_repos(self, username):
        """
        Get all repositories that the user owns or is a collaborator on.

        Args:
        username (str): The username of the user to get repositories for.

        Returns:
        str: Repository list separated by new lines.
        """
        try:
            all_repos = []
            page = 1
            while True:
                response = requests.get(
                    f"https://api.github.com/users/{username}/repos?type=all&page={page}",
                    headers={
                        "Authorization": f"token {self.GITHUB_API_KEY}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                repos = response.json()
                if not repos:
                    break
                all_repos.extend(repos)
                page += 1
            repo_list = []
            for repo in all_repos:
                repo_name = repo["full_name"]
                if not repo["archived"]:
                    repo_list.append(repo_name)
            self.failures = 0
            return f"Repositories for {username}:\n\n" + "\n".join(repo_list)
        except requests.exceptions.RequestException as e:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_user_repos(username)
            return f"Error: {str(e)}"

    async def upload_file_to_repo(
        self,
        repo_url: str,
        file_path: str,
        file_content: str,
        branch: str = "main",
        commit_message: str = "Upload file",
    ) -> str:
        """
        Upload a file to a GitHub repository, creating the branch if it doesn't exist

        Args:
        repo_url (str): The URL of the GitHub repository
        file_path (str): The full path where the file should be stored in the repo
        file_content (str): The content of the file to be uploaded
        branch (str): The branch to upload to (default is "main")
        commit_message (str): The commit message for the file upload

        Returns:
        str: The result of the file upload operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])

            # Check if the branch exists, create it if it doesn't
            try:
                repo.get_branch(branch)
            except Exception:
                # Branch doesn't exist, so create it
                default_branch = repo.default_branch
                source_branch = repo.get_branch(default_branch)
                repo.create_git_ref(
                    ref=f"refs/heads/{branch}", sha=source_branch.commit.sha
                )
            if "/WORKSPACE/" in file_path:
                file_path = file_path.split("/WORKSPACE/")[-1]
            # Check if file already exists
            try:
                contents = repo.get_contents(file_path, ref=branch)
                repo.update_file(
                    contents.path,
                    commit_message,
                    file_content,
                    contents.sha,
                    branch=branch,
                )
                action = "Updated"
            except Exception:
                repo.create_file(file_path, commit_message, file_content, branch=branch)
                action = "Created"

            self.failures = 0
            return f"{action} file '{file_path}' in GitHub Repository at {repo_url} on branch [{branch}]({repo_url}/tree/{branch})"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.upload_file_to_repo(
                    repo_url, file_path, file_content, branch, commit_message
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def create_and_merge_pull_request(
        self,
        repo_url: str,
        title: str,
        body: str,
        head: str,
        base: str,
        merge_method: str = "squash",
    ) -> str:
        """
        Create a new pull request in a GitHub repository and automatically merge it

        Args:
        repo_url (str): The URL of the GitHub repository
        title (str): The title of the pull request
        body (str): The body of the pull request
        head (str): The branch to merge from
        base (str): The branch to merge to
        merge_method (str): The merge method to use (default is "merge", options are "merge", "squash", "rebase")

        Returns:
        str: The result of the pull request creation and merge operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.create_pull(
                title=title, body=body, head=head, base=base
            )
            result = f"Created new pull request #{pull_request.number} `{pull_request.title}`"
            # Check if the pull request can be merged
            if pull_request.mergeable:
                if merge_method == "squash":
                    merge_result = pull_request.merge(merge_method="squash")
                elif merge_method == "rebase":
                    merge_result = pull_request.merge(merge_method="rebase")
                else:
                    merge_result = pull_request.merge()

                if merge_result.merged:
                    result += f" and merged."
                else:
                    result += f". Failed to merge pull request. Reason: {merge_result.message}"
            else:
                result += f". Pull request #{pull_request.number} cannot be merged automatically. Please resolve conflicts and merge manually."
            self.failures = 0
            return result
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.create_and_merge_pull_request(
                    repo_url, title, body, head, base, merge_method
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def reduce_code_content(self, code, task_description):
        """
        Ask the agent to look at the whole code base and determine which files are necessary to complete the task.

        The agent does not need to resolve the task, just tell us what files are relevant if the code base is over 64k tokens.
        """
        tokens = get_tokens(code)
        if tokens > 64000:
            necessary_files = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": f"""### Task Description

{task_description}

### Code Base

{code}

The code base is too large for me to process in one go. Can you help me identify the files that are relevant to the task?

We need the response in the answer block to be in the following format:

<files>
    <file>path/to/file1</file>
    <file>path/to/file2</file>
</files>
""",
                    "context": f"",
                    "log_user_input": False,
                    "disable_commands": True,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "conversation_name": self.conversation_name,
                },
            )
            # Turn the files response into a list
            necessary_files = necessary_files.split("<file>")[1:]
            necessary_files = [file.split("</file>")[0] for file in necessary_files]
            return necessary_files
        return []

    async def improve_codebase(
        self,
        idea: str,
        repo_org: str,
        repo_name: str,
        additional_context: str = "",
    ) -> str:
        """
        Improve the codebase of a GitHub repository by:

        1. Taking an initial idea and produces a GitHub issue that details the tasks needed, or uses an existing issue if provided.
        2. For the issue, prompting the model to produce minimal code modifications using the <modification> XML format.
        3. Applying those modifications to a branch associated with the issue.
        4. Creates a pull request for the issue once completed if one does not already exist.

        - The idea should be well articulated and provide a clear direction of the user's perceived expectations.
        - This command can be used to take a natural language idea and turn it into actioned changes on a new or existing branch.
        - If an issue already exists, it will use that issue to make the changes as long as the issue number is provided in additional_context.

        Args:
            idea (str): The idea to improve the codebase.
            repo_org (str): The organization or username for the GitHub repository.
            repo_name (str): The repository name.
            additional_context (str): Additional context to provide to the model. If an existing issue is mentioned or known for this, mention it here.

        Returns:
            str: A summary message indicating the number of issues and pull requests created.

        Model Behavior:
            - Initially, the model is asked to produce a scope of work and then create issues.
            - For each issue, we prompt the model again to provide minimal code modifications as <modification> blocks.
            - We apply those modifications with `modify_file_content`.

        Example of Expected Model Output for the second prompt per issue:
        <modification>
            <operation>replace</operation>
            <target>def old_function():
            pass</target>
            <content>def old_function():
            return "fixed"</content>
        </modification>
        """
        repo_url = f"https://github.com/{repo_org}/{repo_name}"
        try:
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Reviewing issues on [{repo_org}/{repo_name}]({repo_url}).",
                conversation_name=self.conversation_name,
            )

            # Get existing issues
            issues = await self.get_repo_issues(repo_url=repo_url)
            if issues.startswith("Error:"):
                return f"Failed to get repository issues: {issues}"

            # Ask if any existing issues are related
            issue_response = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": f"""### Idea
{idea}
{additional_context}

### Open Issues
{issues}

Is there an existing issue that is related to the idea you provided? If so, please provide the issue number only in the answer block. If not, respond with 0.""",
                    "context": "",
                    "log_user_input": False,
                    "disable_commands": True,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "conversation_name": self.conversation_name,
                },
            )

            # Extract issue number more robustly
            try:
                if "<answer>" in issue_response:
                    issue_response = issue_response.split("</answer>")[0].split(
                        "<answer>"
                    )[-1]
                issue_number = int("".join(filter(str.isdigit, issue_response)))
            except (ValueError, TypeError):
                issue_number = 0

            if issue_number == 0:
                # Create new issue logic
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Scoping necessary work to implement changes to [{repo_org}/{repo_name}]({repo_url}).",
                    conversation_name=self.conversation_name,
                )

                repo_content = await self.get_repo_code_contents(repo_url=repo_url)

                scope = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": f"""### Presented Idea
{idea}

## User
Please take the presented idea and write a detailed scope for a junior developer to build out the remaining code using the provided code from the repository.
Follow all patterns in the current framework to maintain maintainability and consistency.
The developer may have little to no guidance outside of this scope.""",
                        "context": f"### Content of {repo_url}\n\n{repo_content}\n{additional_context}",
                        "log_user_input": False,
                        "disable_commands": True,
                        "log_output": False,
                        "browse_links": False,
                        "websearch": False,
                        "analyze_user_input": False,
                        "tts": False,
                        "conversation_name": self.conversation_name,
                    },
                )

                # Create issue title
                issue_title = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": f"""### Scope of Work
{scope}

Come up with a concise title for the GitHub issue based on the scope of work, respond with only the title in the answer block.""",
                        "context": f"### Content of {repo_url}\n\n{repo_content}\n{additional_context}",
                        "log_user_input": False,
                        "disable_commands": True,
                        "log_output": False,
                        "browse_links": False,
                        "websearch": False,
                        "analyze_user_input": False,
                        "tts": False,
                        "conversation_name": self.conversation_name,
                    },
                )

                if "<answer>" in issue_title:
                    issue_title = issue_title.split("</answer>")[0].split("<answer>")[
                        -1
                    ]

                repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
                issue = repo.create_issue(title=issue_title, body=scope)
                issue_number = issue.number

                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Created GitHub [issue #{issue_number}: {issue_title}]({issue.html_url}).",
                    conversation_name=self.conversation_name,
                )
            else:
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Using existing GitHub [issue #{issue_number}]({repo_url}/issues/{issue_number}).",
                    conversation_name=self.conversation_name,
                )

            # Fix the GitHub issue
            return await self.fix_github_issue(
                repo_org=repo_org,
                repo_name=repo_name,
                issue_number=str(issue_number),
                additional_context=f"{additional_context}\n{idea}",
            )

        except Exception as e:
            return f"Error improving codebase: {str(e)}"

    async def copy_repo_contents(
        self,
        source_repo_url: str,
        destination_repo_url: str,
        branch: str = "main",
    ) -> str:
        """
        Copy the contents of a source repository to a destination repository without forking.

        Args:
        source_repo_url (str): The URL of the source GitHub repository
        destination_repo_url (str): The URL of the destination GitHub repository
        branch (str): The branch to copy from and to (default is "main")

        Returns:
        str: The result of the repository content copy operation
        """
        try:
            source_repo = self.gh.get_repo(source_repo_url.split("github.com/")[-1])
            dest_repo = self.gh.get_repo(destination_repo_url.split("github.com/")[-1])

            # Get all files from the source repository
            contents = source_repo.get_contents("", ref=branch)
            files_copied = 0

            while contents:
                file_content = contents.pop(0)
                if file_content.type == "dir":
                    contents.extend(
                        source_repo.get_contents(file_content.path, ref=branch)
                    )
                else:
                    try:
                        # Get the file content from the source repo
                        file = source_repo.get_contents(file_content.path, ref=branch)
                        file_data = file.decoded_content

                        # Check if file exists in destination repo
                        try:
                            dest_file = dest_repo.get_contents(
                                file_content.path, ref=branch
                            )
                            # Update existing file
                            dest_repo.update_file(
                                file_content.path,
                                f"Update {file_content.path}",
                                file_data,
                                dest_file.sha,
                                branch=branch,
                            )
                        except Exception:
                            # Create new file if it doesn't exist
                            dest_repo.create_file(
                                file_content.path,
                                f"Create {file_content.path}",
                                file_data,
                                branch=branch,
                            )

                        files_copied += 1

                    except Exception as e:
                        return f"Error copying file {file_content.path}: {str(e)}"

            self.failures = 0
            return f"Successfully copied {files_copied} files from {source_repo_url} to {destination_repo_url} on branch [{branch}]({destination_repo_url}/tree/{branch})"

        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.copy_repo_contents(
                    source_repo_url, destination_repo_url, branch
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    def _try_different_indentations(
        self, content: str, max_indent: int = 3
    ) -> List[str]:
        """Try different indentation levels for a given content block.

        Args:
            content: The code block to process
            max_indent: Maximum number of indentation levels to try (default 3)

        Returns:
            List of content variations with different indentation levels
        """
        variations = []
        lines = content.splitlines()

        # Add original version
        variations.append(content)

        # Try different indentation levels
        for indent_level in range(1, max_indent + 1):
            indented_lines = []
            indent = "    " * indent_level  # 4 spaces per level

            for line in lines:
                if line.strip():  # Only indent non-empty lines
                    indented_lines.append(indent + line)
                else:
                    indented_lines.append(line)

            variations.append("\n".join(indented_lines))

        return variations

    def _handle_insertion_point(
        self, file_lines: List[str], target_line: str
    ) -> tuple[int, int, int]:
        """Handle finding insertion points for new code blocks.

        Args:
            file_lines: List of lines from the file
            target_line: The first line of the target block

        Returns:
            tuple: (insertion_line, insertion_line, indent_level)
        """

        def get_block_end(start_idx: int, base_indent: int) -> int:
            """Find the end of a code block based on indentation."""
            i = start_idx + 1
            while i < len(file_lines):
                line = file_lines[i].rstrip()
                if not line:  # Skip empty lines
                    i += 1
                    continue
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= base_indent:
                    return i
                i += 1
            return i

        # Try exact match first
        matches = []
        target_pattern = target_line.lstrip()

        for i, line in enumerate(file_lines):
            normalized_line = line.lstrip()
            if normalized_line == target_pattern:
                matches.append(i)

        # If no exact match, try fuzzy matching
        if not matches:
            # Extract function/class name from target
            target_name_match = re.search(r"(?:def|class)\s+(\w+)", target_pattern)
            if target_name_match:
                target_name = target_name_match.group(1)

                # Look for similar function/class definitions
                for i, line in enumerate(file_lines):
                    if re.match(r"^(\s*)(async\s+)?(def|class)\s+\w+", line):
                        name_match = re.search(r"(?:def|class)\s+(\w+)", line.lstrip())
                        if name_match:
                            similarity = difflib.SequenceMatcher(
                                None, target_name, name_match.group(1)
                            ).ratio()
                            if (
                                similarity > 0.8
                            ):  # High threshold for function/class names
                                matches.append(i)

        if not matches:
            raise ValueError(f"Could not find insertion point for: {target_line}")

        # Find the end of the best matching block
        best_match_idx = matches[0]
        base_indent = len(file_lines[best_match_idx]) - len(
            file_lines[best_match_idx].lstrip()
        )
        end_idx = get_block_end(best_match_idx, base_indent)

        return end_idx, end_idx, base_indent // 4

    def _parse_modification_block(self, modification_block: str) -> dict:
        """Parse a single modification block into its components.

        Args:
            modification_block (str): Raw XML string containing a single modification

        Returns:
            dict: Parsed modification with operation, target, content, and fuzzy_match
        """
        try:
            # Debug logging
            logging.debug(f"Parsing modification block:\n{modification_block}")

            def escape_code_content(xml_str: str) -> str:
                """Escape code content by wrapping in CDATA sections."""

                def wrap_in_cdata(match):
                    tag_name = match.group(1)
                    content = match.group(2)
                    # Always wrap code content in CDATA
                    return f"<{tag_name}><![CDATA[{content}]]></{tag_name}>"

                # Use a more precise regex that captures the entire tag content
                pattern = r"<(target|content)>(.*?)</\1>"
                return re.sub(pattern, wrap_in_cdata, xml_str, flags=re.DOTALL)

            # First, normalize the XML structure
            clean_xml = re.sub(r"\s+<", "<", modification_block.strip())
            clean_xml = re.sub(r">\s+", ">", clean_xml)
            clean_xml = re.sub(r"\s+</modification>", "</modification>", clean_xml)

            # Then escape the code content
            clean_xml = escape_code_content(clean_xml)

            try:
                root = ET.fromstring(clean_xml)
            except ET.ParseError as xml_error:
                # Enhanced error reporting
                lines = clean_xml.split("\n")
                position = (
                    xml_error.position[0]
                    if isinstance(xml_error.position, tuple)
                    else xml_error.position
                )
                line_num = sum(1 for _ in clean_xml[:position].splitlines())

                # Find the problematic line and show context
                context_lines = []
                for i in range(max(0, line_num - 2), min(len(lines), line_num + 3)):
                    prefix = ">>> " if i == line_num - 1 else "    "
                    context_lines.append(f"{prefix}{lines[i]}")

                error_context = "\n".join(
                    [
                        f"XML Parse Error near line {line_num}:",
                        *context_lines,
                        f"Error details: {str(xml_error)}",
                    ]
                )

                raise ValueError(error_context)

            # Extract components
            try:
                operation = root.find("operation").text.strip()
                if operation not in ["replace", "insert", "delete"]:
                    operation = "replace"  # Default to replace if invalid

                target = root.find("target").text
                if not target:
                    # Start at the beginning of the file if no target specified
                    target = "0"

                content = root.find("content")
                content = content.text if content is not None else None
                if operation in ["replace", "insert"] and not content:
                    content = ""

                fuzzy_match = True
                fuzzy_elem = root.find("fuzzy_match")
                if fuzzy_elem is not None:
                    fuzzy_match = fuzzy_elem.text.lower() != "false"

                return {
                    "operation": operation,
                    "target": target,
                    "content": content,
                    "fuzzy_match": fuzzy_match,
                }

            except AttributeError as e:
                raise ValueError(f"Invalid XML structure: {str(e)}")

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Error parsing modification block: {str(e)}")

    def clean_content(self, content: str) -> str:
        """Clean content by normalizing line endings and removing any leading/trailing whitespace.

        Args:
            content (str): The content to clean

        Returns:
            str: The cleaned content with normalized line endings
        """
        if not content:
            return content

        # Split into lines and clean each one
        lines = content.splitlines()

        # Clean up each line but preserve empty lines and indentation
        cleaned_lines = []
        for line in lines:
            # Only strip trailing whitespace, preserve leading whitespace for indentation
            line = line.rstrip()
            cleaned_lines.append(line)

        # Join lines back together with normalized line endings
        return "\n".join(cleaned_lines)

    def _find_best_matching_file(
        self, repo, file_path: str, branch: str = None
    ) -> tuple[str, float]:
        """
        Find the most similar file in the repository to the given file path.

        Args:
            repo: GitHub repository object
            file_path (str): The target file path to match
            branch (str): The branch to search in, defaults to repository's default branch

        Returns:
            tuple[str, float]: The best matching file path and its similarity score (0-1)
        """
        try:
            if not branch:
                branch = repo.default_branch

            # First try exact match
            try:
                repo.get_contents(file_path, ref=branch)
                return file_path, 1.0
            except Exception:
                pass

            # Get all files in the repository
            contents = repo.get_contents("", ref=branch)
            all_files = []

            while contents:
                file_content = contents.pop(0)
                if file_content.type == "dir":
                    contents.extend(repo.get_contents(file_content.path, ref=branch))
                else:
                    all_files.append(file_content.path)

            # Remove leading slashes and normalize paths
            target_path = file_path.lstrip("/")
            target_parts = target_path.split("/")
            target_name = target_parts[-1]

            best_match = None
            best_score = 0

            for repo_file in all_files:
                repo_file = repo_file.lstrip("/")
                repo_parts = repo_file.split("/")
                repo_name = repo_parts[-1]

                # Calculate name similarity
                name_similarity = difflib.SequenceMatcher(
                    None, target_name, repo_name
                ).ratio()

                # Calculate path similarity
                path_similarity = difflib.SequenceMatcher(
                    None, target_path, repo_file
                ).ratio()

                # Weight name similarity more heavily than path similarity
                combined_score = (name_similarity * 0.7) + (path_similarity * 0.3)

                if combined_score > best_score:
                    best_score = combined_score
                    best_match = repo_file

            return best_match, best_score

        except Exception as e:
            logging.warning(f"Error in _find_best_matching_file: {str(e)}")
            return None, 0.0

    async def modify_file_content(
        self,
        repo_url: str,
        file_path: str,
        modification_commands: str,
        branch: str = None,
    ) -> str:
        """
        Apply a series of modifications to a file while preserving formatting and context.

        Args:
            repo_url (str): The URL of the GitHub repository (e.g., "https://github.com/username/repo")
            file_path (str): Path to the file within the repository (e.g., "src/example.py")
            modification_commands (str): XML formatted string containing one or more modification commands.
            The expected XML format:

            <modification>
                <operation>replace|insert|delete</operation>
                <target>code_block_or_line_number</target>
                <content>new_content (required for replace and insert)</content>
            </modification>

            Multiple <modification> blocks can be provided in a single string.

            branch (str, optional): The branch to modify. Defaults to the repository's default branch.

            Returns:
                str: A unified diff of the changes made, or an error message if something goes wrong.

            Operation Types:
                - replace: Replaces the target code block with new content.
                - insert: Inserts new content at the target location (line number or after a code block).
                - delete: Removes the target code block or line.

            Target Options:
                1. Code block: A string of code to match in the file.
                2. Line number: A specific line number where the operation should occur.

            Fuzzy Matching:
                - "true": Enables smart matching ignoring whitespace differences (default).
                - "false": Requires exact match including whitespace.

            Example:
                <modification>
                    <operation>replace</operation>
                    <target>def old_function():
        pass</target>
                    <content>def old_function():
        return "fixed"</content>
                </modification>

            The method handles indentation and attempts to maintain code style. It returns a diff
            so you can review the changes made.

            Notes:
            - If multiple modifications are requested, they are applied in sequence.
            - If any modification cannot find its target, an exception is raised.

            Returns:
                str: A unified diff showing the changes made or error message
        """
        try:
            retry_count = 0
            max_retries = 3
            errors = []

            while retry_count < max_retries:
                try:
                    # Log attempt
                    logging.info(
                        f"Modification attempt #{retry_count + 1} for {file_path}"
                    )
                    if self.activity_id:
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] Modifying [{file_path}]({repo_url}/blob/{branch}/{file_path}) on branch [{branch}]({repo_url}/tree/{branch}).\n```xml\n{modification_commands}\n```",
                            conversation_name=self.conversation_name,
                        )

                    # Extract and parse each modification block
                    modifications = re.findall(
                        r"<modification>(.*?)</modification>",
                        modification_commands,
                        re.DOTALL,
                    )

                    if not modifications:
                        raise ValueError("No modification blocks found")

                    # Parse each modification into structured data
                    parsed_mods = []
                    for i, mod in enumerate(modifications, 1):
                        try:
                            mod_xml = f"<modification>{mod}</modification>"
                            parsed_mod = self._parse_modification_block(mod_xml)
                            parsed_mods.append(parsed_mod)
                            logging.debug(
                                f"Successfully parsed modification {i}: {parsed_mod['operation']} operation"
                            )
                        except ValueError as e:
                            logging.error(f"Failed to parse modification {i}: {str(e)}")
                            raise ValueError(
                                f"Error in modification block {i}: {str(e)}"
                            )

                    # Get repository
                    repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
                    if not branch:
                        branch = repo.default_branch

                    # Find best matching file or prepare for new file creation
                    best_match, match_score = self._find_best_matching_file(
                        repo, file_path, branch
                    )

                    # Initialize file content and object
                    file_content = ""
                    file_content_obj = None

                    if best_match and match_score >= 0.8:
                        file_path = best_match
                        try:
                            file_content_obj = repo.get_contents(file_path, ref=branch)
                            file_content = file_content_obj.decoded_content.decode(
                                "utf-8"
                            )
                        except Exception:
                            # File might have been deleted or moved
                            pass

                    # Process modifications
                    original_content = file_content
                    modified_content = file_content
                    has_changes = False

                    for mod in parsed_mods:
                        operation = mod["operation"]
                        target = mod["target"]
                        content = mod.get("content")
                        fuzzy_match = True

                        if (operation in ["replace", "insert"]) and not content:
                            raise ValueError(
                                f"Content is required for {operation} operation"
                            )

                        # For empty files or new files, handle differently
                        if not modified_content and operation == "insert":
                            modified_content = content
                            has_changes = True
                            continue

                        # Split content into lines while preserving empty lines
                        modified_lines = modified_content.splitlines(keepends=True)

                        if not modified_lines and operation != "insert":
                            # Can't perform replace or delete on empty file
                            raise ValueError(
                                f"Cannot perform {operation} on empty file"
                            )

                        # Find target location
                        try:
                            start_line, end_line, indent_level = (
                                self._find_pattern_boundaries(
                                    [line.rstrip("\n") for line in modified_lines],
                                    target,
                                    fuzzy_match=fuzzy_match,
                                    operation=operation,
                                )
                            )
                        except ValueError as e:
                            if operation == "insert" and not modified_lines:
                                # New file, just use the content
                                modified_content = content
                                has_changes = True
                                continue
                            raise e

                        # Apply modification
                        if content:
                            content = self.clean_content(content)

                        new_lines = modified_lines[:]
                        if operation == "replace" and content:
                            indent_level = _get_correct_indent_level(
                                modified_lines, start_line
                            )
                            new_content = self._indent_code_block(content, indent_level)
                            new_lines[start_line:end_line] = new_content
                            has_changes = True
                        elif operation == "insert" and content:
                            indent_level = _get_correct_indent_level(
                                modified_lines, start_line
                            )
                            new_content = self._indent_code_block(content, indent_level)
                            # Handle spacing around insertion
                            if (
                                start_line > 0
                                and modified_lines[start_line - 1].strip()
                            ):
                                new_content.insert(0, "\n")
                            if (
                                start_line < len(modified_lines)
                                and modified_lines[start_line].strip()
                            ):
                                new_content.append("\n")

                            new_lines[start_line:start_line] = new_content
                            has_changes = True
                        elif operation == "delete":
                            del new_lines[start_line:end_line]
                            has_changes = True

                        modified_content = "".join(new_lines)

                    if not has_changes:
                        return "No changes needed"

                    # Generate diff
                    diff = list(
                        difflib.unified_diff(
                            original_content.splitlines(),
                            modified_content.splitlines(),
                            fromfile=file_path,
                            tofile=file_path,
                            lineterm="",
                            n=3,
                        )
                    )

                    # Format Python files
                    if self._is_python_file(file_path):
                        modified_content = self._format_python_code(modified_content)
                    elif self._is_js_or_ts_file(file_path):
                        modified_content = self._format_js_ts_code(modified_content)

                    # Ensure final newline
                    if not modified_content.endswith("\n"):
                        modified_content += "\n"

                    commit_message = f"Modified {file_path}"

                    if file_content_obj:
                        # Update existing file
                        repo.update_file(
                            file_path,
                            commit_message,
                            modified_content,
                            file_content_obj.sha,
                            branch=branch,
                        )
                    else:
                        # Create new file
                        repo.create_file(
                            file_path,
                            commit_message,
                            modified_content,
                            branch=branch,
                        )

                    return "\n".join(diff)

                except Exception as e:
                    error_msg = str(e)
                    errors.append(f"Attempt #{retry_count + 1}: {error_msg}")

                    if retry_count >= max_retries - 1:
                        error_history = "\n\nError history:\n" + "\n".join(errors)
                        raise ValueError(
                            f"Failed to apply modifications after {max_retries} attempts. {error_history}"
                        )

                    retry_count += 1
                    logging.warning(
                        f"Modification attempt #{retry_count} failed: {error_msg}"
                    )
        except Exception as e:
            logging.error(f"Modification failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"

    # Helper command methods for individual operations
    async def replace_in_file(
        self,
        repo_url: str,
        file_path: str,
        target: str,
        content: str,
        fuzzy_match: str = "true",
        branch: str = None,
    ) -> str:
        """
        Replace a code block in a file while preserving formatting and indentation.

        Args:
            repo_url (str): The URL of the GitHub repository
            file_path (str): Path to the file within the repository
            target (str): Code block to replace or line number
            content (str): New code to insert in place of target
            fuzzy_match (str): "true" for smart matching ignoring whitespace, "false" for exact match
            branch (str, optional): Branch to modify. Defaults to repository's default branch

        The target can be either:
        1. A code block:
           target="def old_function():
                     pass"
        2. A line number:
           target="42"

        Examples:
            Replace a function:
            <execute>
            <name>Replace in File</name>
            <repo_url>https://github.com/username/repo</repo_url>
            <file_path>src/example.py</file_path>
            <target>def old_function():
                pass</target>
            <content>def new_function(param: str):
                return param.upper()</content>
            </execute>

        Returns:
            str: A unified diff showing the changes made or error message
        """
        if str(content).startswith("\n"):
            content = content[1:]
        if str(content).endswith("\n"):
            content = content[:-1]
        if str(target).startswith("\n"):
            target = target[1:]
        if str(target).endswith("\n"):
            target = target[:-1]
        modification = f"""
<modification>
<operation>replace</operation>
<target>{target}</target>
<content>{content}</content>
<fuzzy_match>true</fuzzy_match>
</modification>
        """
        return await self.modify_file_content(repo_url, file_path, modification, branch)

    async def insert_in_file(
        self,
        repo_url: str,
        file_path: str,
        target: str,
        content: str,
        fuzzy_match: str = "true",
        branch: str = None,
    ) -> str:
        """
        Insert new code at a specific location in a file while preserving formatting.

        Args:
            repo_url (str): The URL of the GitHub repository
            file_path (str): Path to the file within the repository
            target (str): Location to insert code (line number or code block to insert after)
            content (str): New code to insert
            fuzzy_match (str): "true" for smart matching ignoring whitespace, "false" for exact match
            branch (str, optional): Branch to modify. Defaults to repository's default branch

        The target can be either:
        1. A line number where the code should be inserted:
           target="10"
        2. A code block to insert after:
           target="class ExampleClass:"

        Examples:
            Insert a new method:
            <execute>
            <name>Insert in File</name>
            <repo_url>https://github.com/username/repo</repo_url>
            <file_path>src/example.py</file_path>
            <target>class MyClass:</target>
            <content>    def new_method(self):
                return "Hello World"</content>
            </execute>

        Returns:
            str: A unified diff showing the changes made or error message
        """
        modification = f"""
<modification>
<operation>insert</operation>
<target>{target}</target>
<content>{content}</content>
<fuzzy_match>true</fuzzy_match>
</modification>
        """
        return await self.modify_file_content(repo_url, file_path, modification, branch)

    async def delete_from_file(
        self,
        repo_url: str,
        file_path: str,
        target: str,
        fuzzy_match: str = "true",
        branch: str = None,
    ) -> str:
        """
        Delete a code block from a file.

        Args:
            repo_url (str): The URL of the GitHub repository
            file_path (str): Path to the file within the repository
            target (str): Code block to delete or line number range
            fuzzy_match (str): "true" for smart matching ignoring whitespace, "false" for exact match
            branch (str, optional): Branch to modify. Defaults to repository's default branch

        The target can be either:
        1. A code block to remove:
           target="    # Old comment
                      old_variable = None"
        2. A specific line:
           target="42"

        Examples:
            Delete an obsolete function:
            <execute>
            <name>Delete from File</name>
            <repo_url>https://github.com/username/repo</repo_url>
            <file_path>src/example.py</file_path>
            <target>def deprecated_function():
                # This function is no longer used
                pass</target>
            </execute>

        Returns:
            str: A unified diff showing the changes made or error message
        """
        modification = f"""
        <modification>
        <operation>delete</operation>
        <target>{target}</target>
        <fuzzy_match>true</fuzzy_match>
        </modification>
        """
        return await self.modify_file_content(repo_url, file_path, modification, branch)

    async def handle_modifications(
        self,
        prompt: str,
        modifications_xml: str,
        repo_url: str,
        repo_content: str,
        issue_number: str,
        repo_name: str,
        issue_branch: str,
        additional_context: str = "",
    ) -> str:
        # Parse modifications by file
        modifications_blocks = re.findall(
            r"<modification>(.*?)</modification>", modifications_xml, re.DOTALL
        )
        file_mod_map = {}
        for block in modifications_blocks:
            file_match = re.search(r"<file>(.*?)</file>", block, re.DOTALL)
            if not file_match:
                raise Exception("No <file> tag found in a modification block.")
            file_path = file_match.group(1).strip()
            # if it start with the repo name, remove that.
            if file_path.startswith(repo_name):
                file_path = file_path[len(repo_name) + 1 :]

            # Wrap this single block with <modification> for use in modify_file_content
            single_mod_xml = f"<modification>{block}</modification>"

            if file_path not in file_mod_map:
                file_mod_map[file_path] = []
            file_mod_map[file_path].append(single_mod_xml)
        # Initialize result variable
        result = None

        # Apply modifications file by file
        has_error = False
        results = []

        for file_path, mods in file_mod_map.items():
            combined_mods = "".join(mods)
            try:
                result = await self.modify_file_content(
                    repo_url=repo_url,
                    file_path=file_path,
                    modification_commands=combined_mods,
                    branch=issue_branch,
                )
                if result.startswith("Error:"):
                    has_error = True
                    # Run fix github issue with additional context of the retry prompt
                    retry_prompt = f"""{prompt}
Please provide new modification commands that:
1. Only use existing functions/classes as targets
2. Maintain the same intended functionality
3. Use the correct syntax and indentation
4. Only reference existing dependencies and functions
5. Ensure the file path is correct
6. Try something else, like a shorter target that will fit and match better
7. Do not start target or content with a new line, they're exact replacements.
8. Do not use &lt; and &gt; as replacements for < and > in the XML, it is important to use the actual characters as they're directly replaced in the code.
9. Modifications must be in the <answer> block to be parsed!

If multiple modifications are needed, repeat the <modification> block.

The previous modification attempt failed. Here's what I found:

{result}

Original intended changes were:
{combined_mods}

Rewrite the modifications to fix the issue."""
                    # Get new modifications from model
                    new_modifications = self.ApiClient.prompt_agent(
                        agent_name=self.agent_name,
                        prompt_name="Think About It",
                        prompt_args={
                            "user_input": retry_prompt,
                            "context": f"### Content of {repo_url}\n\n{repo_content}\n{additional_context}",
                            "log_user_input": False,
                            "disable_commands": True,
                            "log_output": False,
                            "browse_links": False,
                            "websearch": False,
                            "analyze_user_input": False,
                            "tts": False,
                            "conversation_name": self.conversation_name,
                            "use_smartest": True,
                        },
                    )
                    # Try applying the new modifications
                    try:
                        result = await self.modify_file_content(
                            repo_url=repo_url,
                            file_path=file_path,
                            modification_commands=new_modifications,
                            branch=issue_branch,
                        )
                        if not result.startswith("Error:"):
                            has_error = False
                    except Exception as e:
                        result = f"Error: {str(e)}"

                results.append(result)
            except Exception as e:
                has_error = True
                result = f"Error: {str(e)}"
                results.append(result)

        if has_error:
            error_results = [r for r in results if r.startswith("Error:")]
            error_message = "\n".join(error_results)
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}][ERROR] Failed to fix issue [#{issue_number}]({repo_url}/issues/{issue_number}).\nErrors: {error_message}",
                conversation_name=self.conversation_name,
            )
            return f"Error applying modifications:\n{error_message}"
        else:
            # Combine all results into a single message
            combined_results = "\n\n".join(results)
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Fixed issue [#{issue_number}]({repo_url}/issues/{issue_number}).\nResults:\n{combined_results}",
                conversation_name=self.conversation_name,
            )
            return f"Modifications applied successfully:\n{combined_results}"

    async def fix_github_issue(
        self,
        repo_org: str,
        repo_name: str,
        issue_number: str,
        additional_context: str = "",
    ) -> str:
        """
        Fix a given GitHub issue by applying minimal code modifications to the repository.
        If a PR is already open for this issue's branch, it will not create a new one.
        Instead, it will apply changes to the existing branch and comment on the PR and issue.
        If no PR is open, it creates a new PR and comments on the issue.
        If there was an error previously or revisions need made on the same PR or issue, the assistant can use this same function to retry fixing the issue while providing additional context in additional_context.

        Args:
        repo_org (str): The organization or username for the GitHub repository
        repo_name (str): The repository name
        issue_number (str): The issue number to fix
        additional_context (str): Additional context to provide to the model, if a user mentions anything that could be useful to pass to the coding model, mention it here.

        Returns:
        str: A message indicating the result of the operation
        """
        repo_url = f"https://github.com/{repo_org}/{repo_name}"
        repo = self.gh.get_repo(f"{repo_org}/{repo_name}")
        base_branch = repo.default_branch
        issue_branch = f"issue-{issue_number}"
        # Ensure the issue branch exists
        try:
            repo.get_branch(issue_branch)
        except Exception:
            # Branch doesn't exist, so create it from base_branch
            source_branch = repo.get_branch(base_branch)
            repo.create_git_ref(f"refs/heads/{issue_branch}", source_branch.commit.sha)
        repo_content = await self.get_repo_code_contents(
            repo_url=f"{repo_url}/tree/{issue_branch}"
        )
        # Ensure issue_number is numeric
        issue_number = "".join(filter(str.isdigit, issue_number))
        issue = repo.get_issue(int(issue_number))
        issue_title = issue.title
        issue_body = issue.body
        # Get issue comments into a list with timestamps and users names
        comments = issue.get_comments()
        recent_comments = ""
        for comment in comments:
            recent_comments += (
                f"**{comment.user.login}** at {comment.updated_at}: {comment.body}\n\n"
            )
        # Prompt the model for modifications with file paths
        self.ApiClient.new_conversation_message(
            role=self.agent_name,
            message=f"[SUBACTIVITY][{self.activity_id}] Analyzing code to fix [#{issue_number}]({repo_url}/issues/{issue_number})",
            conversation_name=self.conversation_name,
        )
        prompt = f"""### Issue #{issue_number}: {issue_title}
{issue_body}

## Recent comments on the issue

{recent_comments}

## User
The repository code and additional context should be referenced for this task. Identify the minimal code changes needed to fix this issue.
You must ONLY return the necessary modifications in the following XML format inside of the <answer> block:

<modification>
<file>path/to/file.py</file>
<operation>replace|insert|delete</operation>
<target>original_code_block_or_line_number</target>
<content>new_code_block_if_needed</content>
</modification>

If multiple modifications are needed, repeat the <modification> block.

### Important:
- Each <modification> block must include a <file> tag specifying which file to modify.
- For <target>, you must use one of these formats:
  1. For inserting after a function/method:
     - Use the complete function definition line, e.g., "def verify_email_address(self, code: str = None):"
     - The new content will be inserted after the entire function
  2. For replacing code:
     - Include the exact code block to replace, including correct indentation
     - The first and last lines are especially important for matching
  3. For specific line numbers:
     - Use the line number as a string, e.g., "42"
- Do not use the repository name or WORKSPACE path in file paths
- The file path should be relative to the repository root
- Content must match the indentation style of the target location
- For replace and insert operations, <content> is required
- For delete operations, <content> is not required
- Put your <modification> blocks inside of the <answer> block!
- Ensure indentation is correct in the <content> tag, it is critical for Python code and other languages with strict indentation rules.
- If working with NextJS, remember to include "use client" as the first line of all files declaring components that use client side hooks such as useEffect and useState.
- Do not start target or content with a new line, they're exact replacements.
- Do not use &lt; and &gt; as replacements for < and > in the XML, it is important to use the actual characters as they're directly replaced in the code.
- Modifications must be in the <answer> block to be parsed! They cannot be outside of it.

Example modifications:
1. Insert after a function:
<modification>
<file>auth.py</file>
<operation>insert</operation>
<target>def verify_email_address(self, code: str = None):</target>
<content>    def verify_mfa(self, token: str):
        # Verify MFA token
        pass</content>
</modification>

2. Replace a code block:
<modification>
<file>auth.py</file>
<operation>replace</operation>
<target>    def verify_token(self):
    return True</target>
<content>    def verify_token(self):
    return self.validate_jwt()</content>
</modification>"""
        modifications_xml = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": prompt,
                "context": f"### Content of {repo_url}\n\n{repo_content}\n{additional_context}",
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": False,
                "analyze_user_input": False,
                "tts": False,
                "conversation_name": self.conversation_name,
                "use_smartest": True,
            },
        )
        self.ApiClient.new_conversation_message(
            role=self.agent_name,
            message=f"[SUBACTIVITY][{self.activity_id}] Applying modifications to fix [#{issue_number}]({repo_url}/issues/{issue_number}).\n{modifications_xml}",
            conversation_name=self.conversation_name,
        )
        modifications = await self.handle_modifications(
            prompt=prompt,
            modifications_xml=modifications_xml,
            repo_url=repo_url,
            repo_content=repo_content,
            issue_number=issue_number,
            repo_name=repo_name,
            issue_branch=issue_branch,
            additional_context=additional_context,
        )
        if modifications.startswith("Error"):
            # Retry modifications with additional context
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Retrying modifications with a different approach.",
                conversation_name=self.conversation_name,
            )
            await self.handle_modifications(
                prompt=prompt,
                modifications_xml=modifications_xml,
                repo_url=repo_url,
                repo_content=repo_content,
                issue_number=issue_number,
                repo_name=repo_name,
                issue_branch=issue_branch,
                additional_context=f"{additional_context}\n\nPrevious modifications failed with error:\n{modifications}",
            )

        # Check if a PR already exists for this branch
        open_pulls = repo.get_pulls(state="open", head=f"{repo_org}:{issue_branch}")
        if open_pulls.totalCount > 0:
            # A PR already exists for this branch
            existing_pr = open_pulls[0]

            # Comment on the PR and the issue about the new changes
            comment_body = (
                f"Additional changes have been pushed to the `{issue_branch}` branch:\n\n"
                f"{modifications_xml}"
            )
            existing_pr.create_issue_comment(comment_body)
            issue.create_comment(
                f"Additional changes have been applied to resolve issue [#{issue_number}]({repo_url}/issues/{issue_number}). See [PR #{existing_pr.number}]({repo_url}/pull/{existing_pr.number})."
            )

            # Review the updated PR
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Reviewing updated PR #{existing_pr.number}",
                conversation_name=self.conversation_name,
            )
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=(
                    f"[SUBACTIVITY][{self.activity_id}] Updated the branch [{issue_branch}]({repo_url}/tree/{issue_branch}) for [#{issue_number}]({repo_url}/issues/{issue_number}). "
                    f"Changes are reflected in [PR #{existing_pr.number}]({repo_url}/pull/{existing_pr.number})."
                ),
                conversation_name=self.conversation_name,
            )
            return f"Updated and reviewed [PR #{existing_pr.number}]({repo_url}/pull/{existing_pr.number}) for issue [#{issue_number}]({repo_url}/issues/{issue_number}) with new changes."
        else:
            # No PR exists, create a new one
            pr_body = f"Resolves #{issue_number}\n\nThe following modifications were applied:\n\n{modifications_xml}"
            if "<modification>" in pr_body:
                # Check if the characters before it are "```xml\n", if it isn't, add it.
                if pr_body.find("```xml\n<modification>") == -1:
                    pr_body = pr_body.replace(
                        "<modification>", "```xml\n<modification>"
                    ).replace("</modification>", "</modification>\n```")
            new_pr = repo.create_pull(
                title=f"Fix #{issue_number}: {issue_title}",
                body=pr_body,
                head=issue_branch,
                base=base_branch,
            )

            # Comment on the issue about the new PR
            issue.create_comment(
                f"Created PR #{new_pr.number} to resolve issue #{issue_number}:\n{repo_url}/pull/{new_pr.number}"
            )

            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}][EXECUTION] Fixed issue [#{issue_number}]({repo_url}/issues/{issue_number}) in [{repo_org}/{repo_name}]({repo_url}) with pull request [#{new_pr.number}]({repo_url}/pull/{new_pr.number}).",
                conversation_name=self.conversation_name,
            )
            response = f"""### Issue #{issue_number}
Title: {issue_title}
Body: 
{issue_body}

### Pull Request #{new_pr.number}
Title: {new_pr.title}
Body: 
{pr_body}

I have created and reviewed pull request [#{new_pr.number}]({repo_url}/pull/{new_pr.number}) to fix issue [#{issue_number}]({repo_url}/issues/{issue_number})."""
            return response

    async def get_assigned_issues(self, github_username: str = "None") -> str:
        """
        Get all open issues assigned to a specific GitHub user.

        Args:

        github_username (str): The GitHub username to search for. If the assistant uses "None", it will default to the user's GitHub username automatically.

        Returns:
        str: A list of open issues assigned to the user in markdown format.

        """
        if github_username.lower() == "none":
            github_username = self.GITHUB_USERNAME
        response = requests.get(
            f"https://api.github.com/search/issues",
            headers={
                "Authorization": f"token {self.GITHUB_API_KEY}",
                "Accept": "application/vnd.github.v3+json",
            },
            params={
                "q": f"is:open is:issue assignee:{github_username} archived:false",
            },
        )

        # Check if the response was successful
        if response.status_code == 200:
            issues = response.json().get("items", [])
            issue_string = f"# Issues assigned to {github_username}\n\n"
            for issue in issues:
                issue_string += (
                    f"## [{issue['title']}]({issue['html_url']})\n\n{issue['body']}\n\n"
                )
            return issue_string
        else:
            return f"Failed to fetch issues: {response.status_code} {response.text}"
