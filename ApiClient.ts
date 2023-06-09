import axios from "axios";
import * as dotenv from "dotenv";
// TODO: Need to review to modify some endpoints and add some missing ones.
dotenv.config();
const baseUri = process.env.BASE_URI || "http://localhost:7437";

class ApiClient {
  static async getProviders(): Promise<string[]> {
    const response = await axios.get(`${baseUri}/api/provider`);
    return response.data.providers;
  }

  static async getProviderSettings(providerName: string): Promise<any> {
    const response = await axios.get(`${baseUri}/api/provider/${providerName}`);
    return response.data.settings;
  }

  static async getEmbedProviders(): Promise<string[]> {
    const response = await axios.get(`${baseUri}/api/embedding_providers`);
    return response.data.providers;
  }

  static async addAgent(agentName: string, settings: any = {}): Promise<any> {
    const response = await axios.post(`${baseUri}/api/agent`, {
      agent_name: agentName,
      settings: settings,
    });
    return response.data;
  }

  static async renameAgent(agentName: string, newName: string): Promise<string> {
    const response = await axios.patch(`${baseUri}/api/agent/${agentName}`, {
      new_name: newName,
    });
    return response.data;
  }

  static async updateAgentSettings(agentName: string, settings: any): Promise<string> {
    const response = await axios.put(`${baseUri}/api/agent/${agentName}`, {
      settings: settings,
      agent_name: agentName,
    });
    return response.data.message;
  }

  static async updateAgentCommands(agentName: string, commands: any): Promise<string> {
    const response = await axios.put(`${baseUri}/api/agent/${agentName}/commands`, {
      commands: commands,
      agent_name: agentName,
    });
    return response.data.message;
  }

  static async deleteAgent(agentName: string): Promise<string> {
    const response = await axios.delete(`${baseUri}/api/agent/${agentName}`);
    return response.data.message;
  }

  static async getAgents(): Promise<any[]> {
    const response = await axios.get(`${baseUri}/api/agent`);
    return response.data.agents;
  }

  static async getAgentconfig(agentName: string): Promise<any> {
    const response = await axios.get(`${baseUri}/api/agent/${agentName}`);
    return response.data.agent;
  }

  static async getChatHistory(agentName: string): Promise<any[]> {
    const response = await axios.get(`${baseUri}/api/${agentName}/chat`);
    return response.data.chat_history;
  }

  static async wipeAgentMemories(agentName: string): Promise<string> {
    const response = await axios.delete(`${baseUri}/api/agent/${agentName}/memory`);
    return response.data.message;
  }

  static async instruct(agentName: string, prompt: string): Promise<string> {
    const response = await axios.post(`${baseUri}/api/agent/${agentName}/instruct`, {
      prompt: prompt,
    });
    return response.data.response;
  }

  static async smartinstruct(agentName: string, shots: number, prompt: string): Promise<string> {
    const response = await axios.post(`${baseUri}/api/agent/${agentName}/smartinstruct/${shots}`, {
      prompt: prompt,
    });
    return response.data.response;
  }

  static async chat(agentName: string, prompt: string): Promise<string> {
    const response = await axios.post(`${baseUri}/api/agent/${agentName}/chat`, {
      prompt: prompt,
    });
    return response.data.response;
  }

  static async smartchat(agentName: string, shots: number, prompt: string): Promise<string> {
    const response = await axios.post(`${baseUri}/api/agent/${agentName}/smartchat/${shots}`, {
      prompt: prompt,
    });
    return response.data.response;
  }

  static async getCommands(agentName: string): Promise<any> {
    const response = await axios.get(`${baseUri}/api/agent/${agentName}/command`);
    return response.data.commands;
  }

  static async toggleCommand(agentName: string, commandName: string, enable: boolean): Promise<string> {
    const response = await axios.patch(`${baseUri}/api/agent/${agentName}/command`, {
      command_name: commandName,
      enable: enable,
    });
    return response.data.message;
  }

  static async startTaskAgent(agentName: string, objective: string): Promise<string> {
    const response = await axios.post(`${baseUri}/api/agent/${agentName}/task`, {
      objective: objective,
    });
    try {
      return response.data.message;
    } catch {
      return response.data;
    }
  }

  static async getTasks(agentName: string): Promise<any[]> {
    const response = await axios.get(`${baseUri}/api/agent/${agentName}/tasks`);
    return response.data.tasks;
  }

  static async getTaskOutput(agentName: string): Promise<any> {
    const response = await axios.get(`${baseUri}/api/agent/${agentName}/task`);
    return response.data.output;
  }

  static async getTaskStatus(agentName: string): Promise<any> {
    const response = await axios.get(`${baseUri}/api/agent/${agentName}/task/status`);
    return response.data.status;
  }

  static async getChains(): Promise<string[]> {
    const response = await axios.get(`${baseUri}/api/chain`);
    return response.data;
  }

  static async getChain(chainName: string): Promise<any> {
    const response = await axios.get(`${baseUri}/api/chain/${chainName}`);
    return response.data.chain;
  }

  static async getChainResponses(chainName: string): Promise<any> {
    const response = await axios.get(`${baseUri}/api/chain/${chainName}/responses`);
    return response.data.chain;
  }

  static async runChain(chainName: string): Promise<string> {
    const response = await axios.post(`${baseUri}/api/chain/${chainName}/run`);
    return response.data.message;
  }

  static async addChain(chainName: string): Promise<string> {
    const response = await axios.post(`${baseUri}/api/chain`, {
      chain_name: chainName,
    });
    return response.data.message;
  }

  static async renameChain(chainName: string, newName: string): Promise<string> {
    const response = await axios.put(`${baseUri}/api/chain/${chainName}`, {
      new_name: newName,
    });
    return response.data.message;
  }

  static async deleteChain(chainName: string): Promise<string> {
    const response = await axios.delete(`${baseUri}/api/chain/${chainName}`);
    return response.data.message;
  }

  static async addStep(
    chainName: string,
    stepNumber: number,
    agentName: string,
    promptType: string,
    prompt: any
  ): Promise<string> {
    const response = await axios.post(`${baseUri}/api/chain/${chainName}/step`, {
      step_number: stepNumber,
      agent_name: agentName,
      prompt_type: promptType,
      prompt: prompt,
    });
    return response.data.message;
  }

  static async updateStep(
    chainName: string,
    stepNumber: number,
    agentName: string,
    promptType: string,
    prompt: any
  ): Promise<string> {
    const response = await axios.put(`${baseUri}/api/chain/${chainName}/step/${stepNumber}`, {
      step_number: stepNumber,
      agent_name: agentName,
      prompt_type: promptType,
      prompt: prompt,
    });
    return response.data.message;
  }

  static async moveStep(
    chainName: string,
    oldStepNumber: number,
    newStepNumber: number
  ): Promise<string> {
    const response = await axios.patch(`${baseUri}/api/chain/${chainName}/step/move`, {
      old_step_number: oldStepNumber,
      new_step_number: newStepNumber,
    });
    return response.data.message;
  }

  static async deleteStep(chainName: string, stepNumber: number): Promise<string> {
    const response = await axios.delete(`${baseUri}/api/chain/${chainName}/step/${stepNumber}`);
    return response.data.message;
  }

  static async addPrompt(promptName: string, prompt: string): Promise<string> {
    const response = await axios.post(`${baseUri}/api/prompt`, {
      prompt_name: promptName,
      prompt: prompt,
    });
    return response.data.message;
  }

  static async getPrompt(promptName: string): Promise<any> {
    const response = await axios.get(`${baseUri}/api/prompt/${promptName}`);
    return response.data;
  }

  static async getPrompts(): Promise<string[]> {
    const response = await axios.get(`${baseUri}/api/prompt`);
    return response.data.prompts;
  }

  static async getPromptArgs(promptName: string): Promise<any> {
    const response = await axios.get(`${baseUri}/api/prompt/${promptName}/args`);
    return response.data.prompt_args;
  }

  static async deletePrompt(promptName: string): Promise<string> {
    const response = await axios.delete(`${baseUri}/api/prompt/${promptName}`);
    return response.data.message;
  }

  static async updatePrompt(promptName: string, prompt: string): Promise<string> {
    const response = await axios.put(`${baseUri}/api/prompt/${promptName}`, {
      prompt: prompt,
      prompt_name: promptName,
    });
    return response.data.message;
  }

  static async getExtensionSettings(): Promise<any> {
    const response = await axios.get(`${baseUri}/api/extensions/settings`);
    return response.data.extension_settings;
  }

  static async getCommandArgs(commandName: string): Promise<any> {
    const response = await axios.get(`${baseUri}/api/extensions/${commandName}/args`);
    return response.data.command_args;
  }

  static async learnUrl(agentName: string, url: string): Promise<string> {
    const response = await axios.post(`${baseUri}/api/agent/${agentName}/learn/url`, {
      url: url,
    });
    return response.data.message;
  }

  static async learnFile(agentName: string, fileName: string, fileContent: string): Promise<string> {
    const response = await axios.post(`${baseUri}/api/agent/${agentName}/learn/file`, {
      file_name: fileName,
      file_content: fileContent,
    });
    return response.data.message;
  }
}

export default ApiClient;
