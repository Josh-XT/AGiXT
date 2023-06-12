# Poe
- [Poe](https://poe.com)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Disclaimer

We are not responsible if Poe bans your account for doing this. This may not be consistent with their rules to use their services in this way. This was developed for experimental purposes and we assume no responsibility for how you use it.


## Limitations for Free accounts
- Claude+ (a2_2) has a limit of 3 messages per day. 
- GPT-4 (beaver) has a limit of 1 message per day. 
- Claude-instant-100k (c2_100k) is completely inaccessible for free accounts. 
- For all the other chatbots, there seems to be a rate limit of 10 messages per minute.

## Quick Start Guide

### Get your Poe Token

1. Open Poe and navigate to https://poe.com
2. Press F12 for console
3. Go to Application → Cookies → `p-b`. Copy the value of that cookie. That is your Poe token.

### Update your agent settings
1. Update `Poe_TOKEN` with the value of `p-b`.
2. Select a `bot` from Poe, use the `Model Name` in the table below for your `AI_MODEL` setting.


| Model Name  | Model               |
|-------------|---------------------|
| capybara    | Sage                |
| a2          | Claude-instant      |
| nutria      | Dragonfly           |
| a2_100k     | Claude-instant-100k |
| beaver      | GPT-4               |
| chinchilla  | ChatGPT             |
| a2_2        | Claude+             |

