# AGiXT

[![GitHub](https://img.shields.io/badge/GitHub-Sponsor%20Josh%20XT-blue?logo=github&style=plastic)](https://github.com/sponsors/Josh-XT) [![PayPal](https://img.shields.io/badge/PayPal-Sponsor%20Josh%20XT-blue.svg?logo=paypal&style=plastic)](https://paypal.me/joshxt) [![Ko-Fi](https://img.shields.io/badge/Kofi-Sponsor%20Josh%20XT-blue.svg?logo=kofi&style=plastic)](https://ko-fi.com/joshxt)

[![GitHub](https://img.shields.io/badge/GitHub-AGiXT%20Core-blue?logo=github&style=plastic)](https://github.com/Josh-XT/AGiXT) [![GitHub](https://img.shields.io/badge/GitHub-AGiXT%20Interactive%20UI-blue?logo=github&style=plastic)](https://github.com/AGiXT/Interactive)

[![GitHub](https://img.shields.io/badge/GitHub-AGiXT%20Python%20SDK-blue?logo=github&style=plastic)](https://github.com/AGiXT/python-sdk) [![pypi](https://img.shields.io/badge/pypi-AGiXT%20Python%20SDK-blue?logo=pypi&style=plastic)](https://pypi.org/project/agixtsdk/)

[![GitHub](https://img.shields.io/badge/GitHub-AGiXT%20TypeScript%20SDK-blue?logo=github&style=plastic)](https://github.com/AGiXT/typescript-sdk) [![npm](https://img.shields.io/badge/npm-AGiXT%20TypeScript%20SDK-blue?logo=npm&style=plastic)](https://www.npmjs.com/package/agixt)

[![GitHub](https://img.shields.io/badge/GitHub-AGiXT%20Dart%20SDK-blue?logo=github&style=plastic)](https://github.com/AGiXT/dart-sdk) [![GitHub](https://img.shields.io/badge/GitHub-AGiXT%20Rust%20SDK-blue?logo=github&style=plastic)](https://github.com/birdup000/AGiXT-Rust-Dev)
[![GitHub](https://img.shields.io/badge/GitHub-AGiXT%20Zig%20SDK-blue?logo=github&style=plastic)](https://github.com/birdup000/AGiXT-Zig-SDK)

[![Discord](https://img.shields.io/discord/1097720481970397356?label=Discord&logo=discord&logoColor=white&style=plastic&color=5865f2)](https://discord.gg/d3TkHRZcjD)
[![Twitter](https://img.shields.io/badge/Twitter-Follow_@Josh_XT-blue?logo=twitter&style=plastic)](https://twitter.com/Josh_XT)
[![Pump.fun](https://img.shields.io/badge/Pump.fun-AGiXT-blue)](https://pump.fun/coin/F9TgEJLLRUKDRF16HgjUCdJfJ5BK6ucyiW8uJxVPpump)

![AGiXT_New](https://github.com/user-attachments/assets/14a5c1ae-6af8-4de8-a82e-f24ea52da23f)

> **AGiXT is a comprehensive AI automation platform that transforms how you interact with artificial intelligence. With 40+ built-in extensions, multi-provider support, and enterprise-grade features, AGiXT serves as the central nervous system for your digital and physical environments.**

## 🌟 Overview

AGiXT is not just another AI framework—it's a complete automation platform that bridges the gap between artificial intelligence and real-world applications. Whether you're controlling smart home devices, managing enterprise workflows, trading cryptocurrencies, or developing complex applications, AGiXT provides the tools and infrastructure to make it happen through natural language interactions.

### 🚀 What Makes AGiXT Unique

- **40+ Built-in Extensions**: From Tesla vehicle control to enterprise asset management
- **Multi-Provider Support**: Work with OpenAI, Anthropic, Google, Azure, local models, and more
- **Enterprise-Ready**: OAuth, multi-tenancy, advanced security, and compliance features
- **Natural Language Control**: Manage complex systems through simple conversations
- **Workflow Automation**: Chain multiple services and create sophisticated automation sequences
- **Real-Time Integration**: WebSockets, webhooks, and live data feeds for immediate responses

### 📈 Use Cases & Impact

**🏠 Smart Home Automation**: *"Start my car's climate control, have Roomba clean the house, and arm the security system"*

**💼 Enterprise Operations**: *"Generate quarterly reports from the database, schedule team meetings, and update project status across all platforms"*

**🔗 Blockchain & DeFi**: *"Check my Solana wallet balance, stake 500 SOL with the best validator, and swap tokens on Jupiter DEX"*

**🏥 Health & Fitness**: *"Sync data from all my fitness devices, analyze my sleep trends, and schedule optimal workout times"*

## 🚀 Quick Start Guide

### ⚡ Prerequisites

**Windows and Mac:**

- [Git](https://git-scm.com/downloads)
- [Docker Desktop](https://docs.docker.com/docker-for-windows/install/)
- [Python 3.10+](https://www.python.org/downloads/)

**Linux:**

- [Git](https://git-scm.com/downloads)
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Python 3.10+](https://www.python.org/downloads/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) *(for local GPU models)*

### 📥 Installation

#### Option 1: Docker Installation (Recommended)

```bash
pip install agixt .
agixt start
```

The script automatically handles Docker setup and starts all services.

> 🤖 **ezLocalai Included**: By default, AGiXT starts with [ezLocalai](https://github.com/DevXT-LLC/ezlocalai) for local AI inference. This provides local LLM, vision, TTS, and STT capabilities out of the box. To disable, set `WITH_EZLOCALAI=false` in your environment.
