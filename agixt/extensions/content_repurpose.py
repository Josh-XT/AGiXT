import logging
import json
from Extensions import Extensions
from Globals import getenv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Content Repurpose Extension for AGiXT

This extension provides content recycling capabilities — taking content that
performed well on one platform and reformatting it for other platforms.

Strategy: Take every Reddit post that performed well and turn it into a Twitter
thread. Take every Twitter thread that performed well and turn it into a LinkedIn
post. Take every LinkedIn post that performed well and turn it into a short form
video script. One piece of content becomes 4 pieces across 4 platforms.

This extension is primarily prompt-orchestration — it uses the AI agent's
language capabilities to transform content between formats.
"""


class content_repurpose(Extensions):
    """
    The Content Repurpose extension transforms content between platform formats
    for maximum reach. One piece of content becomes 4+ pieces across platforms.

    The content recycling pipeline:
    1. Reddit post (long-form, value-heavy) → validated by upvotes
    2. Twitter/X thread → same content, thread format
    3. LinkedIn post → professional tone, key takeaways
    4. Short-form video script → hook + value + CTA

    You don't need an audience on Reddit to get hundreds of thousands of views.
    Once content is validated there, recycle it everywhere.
    """

    CATEGORY = "Marketing & Growth"
    friendly_name = "Content Repurpose"

    def __init__(self, **kwargs):
        self.commands = {
            "Content - Reddit to Twitter Thread": self.reddit_to_twitter,
            "Content - Twitter to LinkedIn Post": self.twitter_to_linkedin,
            "Content - Post to Video Script": self.post_to_video_script,
            "Content - Generate Reddit Post": self.generate_reddit_post,
            "Content - Generate Comparison Post": self.generate_comparison_post,
            "Content - Generate Build in Public Post": self.generate_bip_post,
            "Content - Repurpose to All Platforms": self.repurpose_to_all,
            "Content - Generate Outreach DM": self.generate_outreach_dm,
        }

    async def reddit_to_twitter(self, reddit_post_text: str, product_mention: str = ""):
        """
        Transform a Reddit post into a Twitter/X thread format. Takes long-form
        Reddit content and breaks it into engaging tweet-sized chunks.

        Args:
            reddit_post_text (str): The full text of the Reddit post.
            product_mention (str, optional): Your product name to naturally weave in.

        Returns:
            str: Formatted Twitter thread ready to post.
        """
        try:
            # Split content into logical sections
            paragraphs = [p.strip() for p in reddit_post_text.split("\n") if p.strip()]

            result = "**Twitter Thread Draft:**\n\n"
            result += "*Post each numbered item as a separate tweet:*\n\n"

            # Tweet 1: Hook (from title or first paragraph)
            hook = paragraphs[0] if paragraphs else reddit_post_text[:250]
            if len(hook) > 280:
                hook = hook[:277] + "..."
            result += f"**1/ (Hook)**\n{hook}\n\n🧵👇\n\n"

            # Middle tweets: Value content
            tweet_num = 2
            for para in paragraphs[1:]:
                if len(para) <= 280:
                    result += f"**{tweet_num}/**\n{para}\n\n"
                    tweet_num += 1
                else:
                    # Split long paragraphs
                    sentences = para.replace(". ", ".\n").split("\n")
                    current_tweet = ""
                    for sentence in sentences:
                        if len(current_tweet + sentence) <= 275:
                            current_tweet += sentence + " "
                        else:
                            if current_tweet.strip():
                                result += (
                                    f"**{tweet_num}/**\n{current_tweet.strip()}\n\n"
                                )
                                tweet_num += 1
                            current_tweet = sentence + " "
                    if current_tweet.strip():
                        result += f"**{tweet_num}/**\n{current_tweet.strip()}\n\n"
                        tweet_num += 1

            # Final tweet: CTA
            if product_mention:
                result += f"**{tweet_num}/ (CTA)**\n"
                result += f"I built {product_mention} to solve this.\n\n"
                result += "If you're dealing with this problem, DM me — happy to show you how it works.\n\n"
                result += f"Follow me for more threads like this."
            else:
                result += f"**{tweet_num}/ (CTA)**\n"
                result += (
                    "If this was helpful, follow me for more threads like this.\n\n"
                )
                result += (
                    "Drop a 🔥 if you want me to go deeper on any of these points."
                )

            result += (
                "\n\n---\n"
                "**Posting tips:**\n"
                "- Post at 8-10 AM or 5-7 PM EST for best engagement\n"
                "- Reply to every comment in the first hour\n"
                "- Quote-tweet the thread 4-6 hours later with a key insight\n"
                "- Screenshot the best part for an engagement tweet tomorrow"
            )

            return result

        except Exception as e:
            return f"Error converting to Twitter thread: {str(e)}"

    async def twitter_to_linkedin(
        self, thread_text: str, professional_context: str = ""
    ):
        """
        Transform a Twitter thread into a LinkedIn post format. Adjusts tone
        for professional audience and restructures for LinkedIn's algorithm.

        Args:
            thread_text (str): The Twitter thread text (all tweets combined).
            professional_context (str, optional): Additional professional context to add.

        Returns:
            str: Formatted LinkedIn post ready to publish.
        """
        try:
            # Clean up thread numbering
            import re

            clean_text = re.sub(r"\d+/\s*", "", thread_text)
            clean_text = re.sub(r"🧵👇", "", clean_text)
            clean_text = clean_text.strip()

            paragraphs = [p.strip() for p in clean_text.split("\n") if p.strip()]

            result = "**LinkedIn Post Draft:**\n\n"

            # LinkedIn hook (first line is critical — it shows before "see more")
            hook = paragraphs[0] if paragraphs else clean_text[:150]
            result += f"{hook}\n\n"

            # Add professional context
            if professional_context:
                result += f"{professional_context}\n\n"

            # Body: Key takeaways format (LinkedIn loves numbered lists)
            result += "Here's what I learned:\n\n"
            for i, para in enumerate(paragraphs[1:], 1):
                if len(para) > 20:  # Skip very short fragments
                    result += f"→ {para}\n\n"

            # LinkedIn CTA
            result += (
                "---\n\n"
                "What's your experience with this? Drop your thoughts below 👇\n\n"
                "♻️ Repost this if it resonated with you.\n"
                "🔔 Follow me for more insights like this."
            )

            result += (
                "\n\n---\n"
                "**LinkedIn posting tips:**\n"
                "- Post between 7-9 AM on Tuesday-Thursday\n"
                "- The first line is everything (shows before 'see more')\n"
                "- Reply to every comment in the first 2 hours\n"
                "- Use line breaks liberally — walls of text don't work\n"
                "- Engage with 10-15 other posts before and after posting"
            )

            return result

        except Exception as e:
            return f"Error converting to LinkedIn post: {str(e)}"

    async def post_to_video_script(self, post_text: str, video_length: str = "60"):
        """
        Transform a written post into a short-form video script (TikTok, Reels, Shorts).

        Args:
            post_text (str): The post text to convert into a video script.
            video_length (str): Target video length in seconds. Default "60".

        Returns:
            str: Video script with hooks, transitions, and CTA.
        """
        try:
            paragraphs = [p.strip() for p in post_text.split("\n") if p.strip()]

            result = f"**Short-Form Video Script ({video_length}s):**\n\n"

            # Hook (first 3 seconds)
            result += "## HOOK (0-3 seconds)\n"
            result += "*Look directly at camera, speak with energy:*\n\n"
            hook = paragraphs[0] if paragraphs else post_text[:100]
            result += f'"{hook}"\n\n'

            # Body (main content)
            result += "## BODY (3-50 seconds)\n"
            result += "*Quick cuts, high energy, use text overlays:*\n\n"

            key_points = paragraphs[1:6] if len(paragraphs) > 1 else [post_text]
            for i, point in enumerate(key_points, 1):
                if len(point) > 100:
                    point = point[:100] + "..."
                result += f'**Point {i}:** "{point}"\n'
                result += f"*[Text overlay: key phrase from point]*\n\n"

            # CTA
            result += f"## CTA (last {int(video_length) - 50 if int(video_length) > 50 else 10} seconds)\n"
            result += "*Direct to camera:*\n\n"
            result += (
                '"Follow for more [niche] content."\n'
                '"Link in bio if you want to try it yourself."\n\n'
            )

            result += (
                "---\n"
                "**Video tips:**\n"
                "- Film vertically (9:16)\n"
                "- Add captions/subtitles (80% watch without sound)\n"
                "- Use trending audio if relevant\n"
                "- Post at 7 PM local time\n"
                "- PUT YOUR FACE ON EVERYTHING — people trust people not logos"
            )

            return result

        except Exception as e:
            return f"Error generating video script: {str(e)}"

    async def generate_reddit_post(
        self,
        topic: str,
        product_name: str = "",
        product_description: str = "",
        target_subreddits: str = "",
    ):
        """
        Generate a Reddit-optimized post that provides genuine value while
        naturally mentioning your product. 80% value, 20% product.

        Formats that work:
        - "I built X and here's what I learned"
        - "Here's how to solve [problem] step by step"
        - "I analyzed [data] and here's what I found"

        Args:
            topic (str): The topic or problem to write about.
            product_name (str, optional): Your product name.
            product_description (str, optional): One-line product description.
            target_subreddits (str, optional): Comma-separated target subreddits.

        Returns:
            str: Reddit post draft optimized for engagement.
        """
        try:
            result = "**Reddit Post Draft:**\n\n"

            # Title options
            result += "## Title Options (pick one):\n\n"
            result += f"1. I built a tool to solve {topic} and here's what I learned\n"
            result += f"2. Here's how to {topic} step by step (no BS)\n"
            result += (
                f"3. I spent 6 months studying {topic}. Here's everything I found.\n"
            )
            result += f"4. The biggest mistakes people make with {topic} (and how to fix them)\n\n"

            # Post body
            result += "## Post Body:\n\n"
            result += f"**Opening (hook):**\n"
            result += (
                f"Start with a relatable problem or surprising insight about {topic}.\n"
            )
            result += (
                "Something like: 'I was frustrated with [specific problem]...'\n\n"
            )

            result += "**Value section (80% of the post):**\n"
            result += "- Share 5-7 actionable tips or insights\n"
            result += "- Include specific examples and data\n"
            result += "- Be genuinely helpful — this should stand alone without any product mention\n"
            result += "- Use numbered lists and bold headers for readability\n\n"

            if product_name:
                result += f"**Product mention (between first and last paragraph):**\n"
                result += f"Naturally weave in: 'I ended up building {product_name} "
                result += f"({product_description}) to solve this...'\n"
                result += "Include 2+ other links in the post so it doesn't look promotional.\n"
                result += "Link to genuinely useful resources related to the topic.\n\n"

            result += "**Closing:**\n"
            result += "End with a question to drive comments.\n"
            result += "'What's been your experience with this? What am I missing?'\n\n"

            if target_subreddits:
                subs = [s.strip() for s in target_subreddits.split(",")]
                result += "## Target Subreddits:\n\n"
                for sub in subs:
                    result += f"- r/{sub.replace('r/', '')}\n"
                result += "\n"

            result += (
                "## Rules to follow:\n\n"
                "- Make 80% of the post pure value\n"
                "- Don't post 'hey check out my product' — you'll get banned\n"
                "- Include at least 2 additional links beyond your product\n"
                "- Mention your product between the first and last paragraph\n"
                "- Post in 3-5 subreddits where your customers hang out\n"
                "- Reply to every comment to boost the post in the algorithm"
            )

            return result

        except Exception as e:
            return f"Error generating Reddit post: {str(e)}"

    async def generate_comparison_post(
        self,
        your_product: str,
        competitor: str,
        your_strengths: str = "",
        competitor_weaknesses: str = "",
    ):
        """
        Generate an honest comparison post between your product and a competitor.
        Can be used for blog posts, Reddit, or landing pages.

        Args:
            your_product (str): Your product name.
            competitor (str): Competitor product name.
            your_strengths (str, optional): Comma-separated list of your product's strengths.
            competitor_weaknesses (str, optional): Comma-separated known competitor weaknesses.

        Returns:
            str: Comparison content draft.
        """
        try:
            strengths = (
                [s.strip() for s in your_strengths.split(",") if s.strip()]
                if your_strengths
                else []
            )
            weaknesses = (
                [w.strip() for w in competitor_weaknesses.split(",") if w.strip()]
                if competitor_weaknesses
                else []
            )

            result = f"**{your_product} vs {competitor} — Comparison Draft:**\n\n"

            result += f"## Page Title: {your_product} vs {competitor}: Honest Comparison (2026)\n"
            result += f"## URL: /{your_product.lower().replace(' ', '-')}-vs-{competitor.lower().replace(' ', '-')}\n\n"

            result += "## TL;DR\n\n"
            result += f"| Feature | {your_product} | {competitor} |\n"
            result += f"|---------|{'---' * 5}|{'---' * 5}|\n"
            if strengths:
                for s in strengths[:5]:
                    result += f"| {s} | ✅ | ❌/⚠️ |\n"
            result += f"| Pricing | [Your pricing] | [Their pricing] |\n\n"

            result += "## Overview\n\n"
            result += f"Both {your_product} and {competitor} aim to solve [problem]. "
            result += "Here's an honest breakdown of how they compare.\n\n"

            result += "## Where We're Different\n\n"
            if strengths:
                for strength in strengths:
                    result += f"### {strength}\n"
                    result += (
                        f"[Explain how {your_product} handles this vs {competitor}]\n\n"
                    )

            if weaknesses:
                result += f"## Common {competitor} Pain Points\n\n"
                result += f"Based on user reviews:\n"
                for w in weaknesses:
                    result += f"- {w}\n"
                result += "\n"

            result += "## Pricing Comparison\n\n"
            result += "[Include transparent pricing breakdown]\n\n"

            result += f"## Who Should Use {competitor}\n\n"
            result += "Be honest — don't trash them. Just show where each product fits best.\n\n"

            result += f"## Who Should Use {your_product}\n\n"
            result += "[Describe your ideal customer]\n\n"

            result += "## Migration Guide\n\n"
            result += f"Switching from {competitor}? Here's how to get started:\n"
            result += "1. [Step 1]\n2. [Step 2]\n3. [Step 3]\n\n"

            result += (
                "---\n"
                "**Tips for comparison pages:**\n"
                "- Write honest comparisons — don't trash the competitor\n"
                "- Include real screenshots of both products\n"
                "- Update monthly with fresh data and pricing changes\n"
                "- These rank fast because people search for them before buying\n"
                "- Every visitor to this page has buying intent"
            )

            return result

        except Exception as e:
            return f"Error generating comparison post: {str(e)}"

    async def generate_bip_post(
        self, milestone: str, details: str = "", platform: str = "twitter"
    ):
        """
        Generate a "build in public" post about a milestone, failure, or lesson.
        Building in public is THE strategy — the audience you build while building
        the product becomes the distribution for the product.

        Args:
            milestone (str): The milestone, failure, or lesson to share (e.g., "hit $500 MRR", "lost first user").
            details (str, optional): Additional context and learnings.
            platform (str): Target platform - 'twitter', 'linkedin', 'reddit'. Default 'twitter'.

        Returns:
            str: Build-in-public post draft.
        """
        try:
            result = f"**Build in Public Post ({platform}):**\n\n"

            if platform == "twitter":
                result += f"**Main tweet:**\n{milestone}\n\n"
                if details:
                    result += "**Thread continuation:**\n"
                    result += f"Here's what happened:\n\n{details}\n\n"
                result += (
                    "**Post templates:**\n"
                    f'- "Just hit {milestone}. Took me X months. Here\'s what actually moved the needle:"\n'
                    f'- "I tried {milestone} today and it completely failed. Here\'s what I learned:"\n'
                    f'- "{milestone}. Asked them why. Their answer changed how I think about [topic]:"\n\n'
                )

            elif platform == "linkedin":
                result += f"**Hook:**\n{milestone}\n\n"
                result += "Here's the story:\n\n"
                if details:
                    result += f"{details}\n\n"
                result += "**Key takeaway:**\n[What you learned]\n\n"
                result += "What would you have done differently? 👇\n\n"

            elif platform == "reddit":
                result += f"**Title:** {milestone}\n\n"
                result += (
                    f"**Body:**\nHey everyone, wanted to share something real.\n\n"
                )
                if details:
                    result += f"{details}\n\n"
                result += "Would love to hear if anyone else has experienced this.\n\n"

            result += (
                "---\n"
                "**Build in public tips:**\n"
                "- PUT YOUR FACE ON EVERYTHING\n"
                "- Share failures, losses, wins, lessons — all of it, raw and unfiltered\n"
                "- Nobody wants to follow a faceless SaaS account\n"
                "- Consistency beats quality — a mid post every day beats a perfect post once a week\n"
                "- The audience you build become the distribution for the product"
            )

            return result

        except Exception as e:
            return f"Error generating build-in-public post: {str(e)}"

    async def repurpose_to_all(self, original_content: str, product_name: str = ""):
        """
        Take one piece of content and create drafts for all platforms:
        Reddit, Twitter/X, LinkedIn, and short-form video.

        Args:
            original_content (str): The original content to repurpose.
            product_name (str, optional): Product name to naturally include.

        Returns:
            str: Content drafts for all 4 platforms.
        """
        try:
            result = "# Content Repurposed for All Platforms\n\n"
            result += "*One piece of content → 4 pieces across 4 platforms*\n\n"
            result += "---\n\n"

            # Reddit version
            result += "## 1. Reddit Post\n\n"
            reddit = await self.generate_reddit_post(
                topic=original_content[:100],
                product_name=product_name,
            )
            result += reddit + "\n\n---\n\n"

            # Twitter version
            result += "## 2. Twitter/X Thread\n\n"
            twitter = await self.reddit_to_twitter(original_content, product_name)
            result += twitter + "\n\n---\n\n"

            # LinkedIn version
            result += "## 3. LinkedIn Post\n\n"
            linkedin = await self.twitter_to_linkedin(original_content)
            result += linkedin + "\n\n---\n\n"

            # Video script
            result += "## 4. Short-Form Video Script\n\n"
            video = await self.post_to_video_script(original_content)
            result += video

            return result

        except Exception as e:
            return f"Error repurposing content: {str(e)}"

    async def generate_outreach_dm(
        self,
        context: str,
        platform: str = "reddit",
        person_name: str = "",
        their_problem: str = "",
        your_product: str = "",
    ):
        """
        Generate a personalized outreach DM that doesn't feel like a cold pitch.
        Each message should be specific to the person and thread — not copy-pasted.

        Args:
            context (str): Context about where you found this person (thread title, their comment, review).
            platform (str): Platform for the DM - 'reddit', 'twitter', 'linkedin'. Default 'reddit'.
            person_name (str, optional): Person's name or username.
            their_problem (str, optional): The specific problem they mentioned.
            your_product (str, optional): Your product name.

        Returns:
            str: Personalized DM draft with outreach strategy.
        """
        try:
            name_display = person_name if person_name else "[their name/username]"
            problem = their_problem if their_problem else "[the problem they mentioned]"

            result = f"**Outreach DM Draft ({platform}):**\n\n"

            if platform == "reddit":
                result += "**Subject:** Quick question about your post\n\n"
                result += f"**Message:**\n"
                result += f"Hey {name_display},\n\n"
                result += f"Saw your post/comment about {problem}. "
                result += "I totally get the frustration — I ran into the exact same thing.\n\n"
                result += f"[Reference something specific they said from: {context[:200]}]\n\n"
                result += "What ended up working for me was [genuine advice related to their problem].\n\n"
                if your_product:
                    result += (
                        f"I ended up building {your_product} to solve this for myself. "
                    )
                    result += "Happy to show you if you're interested, no pressure.\n\n"
                result += "Either way, hope that helps!"

            elif platform == "twitter":
                result += f"**Message:**\n"
                result += f"Hey {name_display} — saw your tweet about {problem}.\n\n"
                result += "Dealt with the exact same thing. Quick question: "
                result += "what have you tried so far?\n\n"
                result += "[Wait for response before mentioning product]"

            elif platform == "linkedin":
                result += f"**Connection Note (300 char max):**\n"
                result += f"Hi {name_display}, saw your review/post about {problem}. "
                result += (
                    "Curious what you ended up switching to? Would love to connect.\n\n"
                )
                result += f"**Follow-up message (after they accept):**\n"
                result += f"Thanks for connecting! Was genuinely curious about your experience with {problem}.\n\n"
                result += "[Let them talk first, then mention product naturally]"

            result += (
                "\n\n---\n"
                "**DM outreach rules:**\n"
                "- NOT copy-pasted — each one specific to the thread/person\n"
                "- Answer their question first, mention product at the end\n"
                "- This converts at 30-40% because they already told you they have the problem\n"
                "- Do 10-15 personalized DMs per day\n"
                "- Follow up 3 days later: 'Hey, how's it going?'\n"
                "- Don't send a link — start a conversation first\n"
                "- Speed matters — the first helpful reply wins"
            )

            return result

        except Exception as e:
            return f"Error generating outreach DM: {str(e)}"
