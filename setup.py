from setuptools import setup, find_packages
import os

# Read the contents of your README file
this_directory = os.path.dirname(os.path.realpath(__file__))
readme_path = os.path.join(this_directory, "docs", "README.md")

# Read the contents of the README file
with open(readme_path, encoding="utf-8") as f:
    long_description = f.read()

# Full requirements from requirements.txt (only needed for local server mode)
with open(os.path.join(this_directory, "requirements.txt"), encoding="utf-8") as f:
    install_requires = f.read().splitlines()
full_requirements = []
for reqs in install_requires:
    if "--" not in reqs and ":" not in reqs and "#" not in reqs:
        full_requirements.append(reqs)

# CLI-only requirements (lightweight - just what the CLI needs)
cli_requirements = [
    "python-dotenv>=1.0.0",
    "requests>=2.28.0",
    "websocket-client>=1.6.0",
    "pyotp",
]

# Get version from version file in agixt/version
with open(os.path.join(this_directory, "agixt/version"), encoding="utf-8") as f:
    version = f.read().strip()

setup(
    name="agixt",
    version=version,
    description="An Artificial Intelligence Automation Platform. AI Instruction management from various providers, has an adaptive memory, and a versatile plugin system with many commands including web browsing. Supports many AI providers and models and growing support every day.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Josh XT",
    author_email="josh@devxt.com",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=cli_requirements,
    extras_require={
        "local": full_requirements,
    },
    entry_points={
        "console_scripts": ["agixt=agixt.cli:main"],
    },
)
