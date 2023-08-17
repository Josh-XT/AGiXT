# Things to Consider
To attempt to manage expectations, here are some things to consider when using AGiXT with large language models.

## Context and Token Limits

Think of AI like a speed-reader with a short-term memory. It can scan through a lot of information quickly, but it can't hold all of it in its mind at once. This limit to what it can remember at any given time is what we call its 'token limit'.

If you hand the AI a huge book and ask, "What's the entire premise of this story?", it can't answer right away. It's like asking someone to read a whole book in a split second and summarize it instantly. The AI, like a human, doesn't have the time (or token capacity) to process all that information at once.

However, if you ask a more specific question like, "What color is Sally's hair in the book?", the AI doesn't need to go through the entire book. It can scan quickly to find that specific information. That's because this question only requires context about Sally's hair, not the entire book.

In other words, different tasks require different amounts of context. A full technical review might need to consider the whole document, as it needs a comprehensive understanding. But a single step of the review could focus on a specific aspect, requiring less context. It's all about matching the AI's token capacity to the task at hand.

## Local Model Expectations

While it is absolutely fascinating to run local models, it is important to understand that they are not very good at making decisions currently. This seems to apply to most models that can currently be run locally (as of August 16, 2023.) This is only being mentioned to help manage expectations of what local models can do. They are great for generating text and can absolutely be used for many things within AGiXT, but I would not recommend giving local models command access due to their lower logical reasoning capabilities. You may get poor results attempting autonomous execution with local models.  Local models are best utilized within Chains where you define to run commands based the text responses that you predefine and the LLM never knows that it can or cannot run commands.  This is the best way to utilize local models in AGiXT currently.
