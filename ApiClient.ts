import axios from 'axios';

export interface ApiResponse<T = any> {
  message: string;
  data: T;
}

export interface PromptArgs {
  [key: string]: any;
}

export interface CommandArgs {
  [key: string]: any;
}

export class ApiClient {
  private baseUri: string;

  constructor(baseUri: string = 'http://localhost:7437') {
    this.baseUri = baseUri;
  }

  public getProviders(): Promise<string[]> {
    return axios.get(`${this.baseUri}/api/provider`).then((response) => response.data.providers);
  }

  public getProviderSettings(providerName: string): Promise<any> {
    return axios.get(`${this.baseUri}/api/provider/${providerName}`).then((response) => response.data.settings);
  }

  public getEmbedProviders(): Promise<string[]> {
    return axios.get(`${this.baseUri}/api/embedding_providers`).then((response) => response.data.providers);
  }

  public addAgent(agentName: string, settings: any = {}): Promise<any> {
    return axios.post(`${this.baseUri}/api/agent`, { agent_name: agentName, settings }).then((response) => response.data);
  }

  public importAgent(agentName: string, settings: any = {}, commands: any = {}): Promise<any> {
    return axios
      .post(`${this.baseUri}/api/agent/import`, { agent_name: agentName, settings, commands })
      .then((response) => response.data);
  }

  public renameAgent(agentName: string, newName: string): Promise<string> {
    return axios
      .patch(`${this.baseUri}/api/agent/${agentName}`, { new_name: newName })
      .then((response) => response.data);
  }

  public updateAgentSettings(agentName: string, settings: any): Promise<string> {
    return axios
      .put(`${this.baseUri}/api/agent/${agentName}`, { settings, agent_name: agentName })
      .then((response) => response.data.message);
  }

  public updateAgentCommands(agentName: string, commands: any): Promise<string> {
    return axios
      .put(`${this.baseUri}/api/agent/${agentName}/commands`, { commands, agent_name: agentName })
      .then((response) => response.data.message);
  }

  public deleteAgent(agentName: string): Promise<string> {
    return axios.delete(`${this.baseUri}/api/agent/${agentName}`).then((response) => response.data.message);
  }

  public getAgents(): Promise<any[]> {
    return axios.get(`${this.baseUri}/api/agent`).then((response) => response.data.agents);
  }

  public getAgentConfig(agentName: string): Promise<any> {
    return axios.get(`${this.baseUri}/api/agent/${agentName}`).then((response) => response.data.agent);
  }

  public getChatHistory(agentName: string): Promise<any[]> {
    return axios.get(`${this.baseUri}/api/${agentName}/chat`).then((response) => response.data.chat_history);
  }

  public deleteAgentHistory(agentName: string): Promise<string> {
    return axios.delete(`${this.baseUri}/api/agent/${agentName}/history`).then((response) => response.data.message);
  }

  public deleteHistoryMessage(agentName: string, message: string): Promise<string> {
    return axios
      .delete(`${this.baseUri}/api/agent/${agentName}/history/message`, { data: { message } })
      .then((response) => response.data.message);
  }

  public wipeAgentMemories(agentName: string): Promise<string> {
    return axios.delete(`${this.baseUri}/api/agent/${agentName}/memory`).then((response) => response.data.message);
  }

  public promptAgent(
    agentName: string,
    promptName: number,
    promptArgs: any,
    userInput: string = '',
    websearch: boolean = false,
    websearchDepth: number = 3,
    contextResults: number = 5,
    shots: number = 1
  ): Promise<string> {
    return axios
      .post(`${this.baseUri}/api/agent/${agentName}/prompt`, {
        user_input: userInput,
        prompt_name: promptName,
        prompt_args: promptArgs,
        websearch,
        websearch_depth: websearchDepth,
        context_results: contextResults,
      })
      .then((response) => {
        if (shots > 1) {
          const responses: string[] = [response.data.response];
          const requests: Promise<any>[] = [];

          for (let shot = 0; shot < shots - 1; shot++) {
            requests.push(
              axios.post(`${this.baseUri}/api/agent/${agentName}/prompt`, {
                user_input: userInput,
                prompt_name: promptName,
                prompt_args: promptArgs,
                context_results: contextResults,
              })
            );
          }

          return Promise.all(requests).then((responses) => {
            responses.forEach((res) => {
              responses.push(res.data.response);
            });
            return responses.join('\n');
          });
        } else {
          return response.data.response;
        }
      });
  }

  public instruct(agentName: string, prompt: string): Promise<string> {
    return axios
      .post(`${this.baseUri}/api/agent/${agentName}/instruct`, { prompt })
      .then((response) => response.data.response);
  }

  public smartinstruct(agentName: string, shots: number, prompt: string): Promise<string> {
    return axios
      .post(`${this.baseUri}/api/agent/${agentName}/smartinstruct/${shots}`, { prompt })
      .then((response) => response.data.response);
  }

  public chat(agentName: string, prompt: string): Promise<string> {
    return axios
      .post(`${this.baseUri}/api/agent/${agentName}/chat`, { prompt })
      .then((response) => response.data.response);
  }

  public smartchat(agentName: string, shots: number, prompt: string): Promise<string> {
    return axios
      .post(`${this.baseUri}/api/agent/${agentName}/smartchat/${shots}`, { prompt })
      .then((response) => response.data.response);
  }

  public getCommands(agentName: string): Promise<{ [key: string]: boolean }> {
    return axios.get(`${this.baseUri}/api/agent/${agentName}/command`).then((response) => response.data.commands);
  }

  public toggleCommand(agentName: string, commandName: string, enable: boolean): Promise<string> {
    return axios
      .patch(`${this.baseUri}/api/agent/${agentName}/command`, { command_name: commandName, enable })
      .then((response) => response.data.message);
  }

  public getChains(): Promise<string[]> {
    return axios.get(`${this.baseUri}/api/chain`).then((response) => response.data);
  }

  public getChain(chainName: string): Promise<any> {
    return axios.get(`${this.baseUri}/api/chain/${chainName}`).then((response) => response.data.chain);
  }

  public getChainResponses(chainName: string): Promise<any> {
    return axios.get(`${this.baseUri}/api/chain/${chainName}/responses`).then((response) => response.data.chain);
  }

  public runChain(chainName: string, userInput: string, agentName: string = ''): Promise<string> {
    return axios
      .post(`${this.baseUri}/api/chain/${chainName}/run`, { prompt: userInput, agent_override: agentName })
      .then((response) => response.data);
  }

  public addChain(chainName: string): Promise<string> {
    return axios.post(`${this.baseUri}/api/chain`, { chain_name: chainName }).then((response) => response.data.message);
  }

  public importChain(chainName: string, steps: any): Promise<string> {
    return axios
      .post(`${this.baseUri}/api/chain/import`, { chain_name: chainName, steps })
      .then((response) => response.data.message);
  }

  public renameChain(chainName: string, newName: string): Promise<string> {
    return axios
      .put(`${this.baseUri}/api/chain/${chainName}`, { new_name: newName })
      .then((response) => response.data.message);
  }

  public deleteChain(chainName: string): Promise<string> {
    return axios.delete(`${this.baseUri}/api/chain/${chainName}`).then((response) => response.data.message);
  }

  public addStep(
    chainName: string,
    stepNumber: number,
    agentName: string,
    promptType: string,
    prompt: any
  ): Promise<string> {
    return axios
      .post(`${this.baseUri}/api/chain/${chainName}/step`, {
        step_number: stepNumber,
        agent_name: agentName,
        prompt_type: promptType,
        prompt,
      })
      .then((response) => response.data.message);
  }

  public updateStep(
    chainName: string,
    stepNumber: number,
    agentName: string,
    promptType: string,
    prompt: any
  ): Promise<string> {
    return axios
      .put(`${this.baseUri}/api/chain/${chainName}/step/${stepNumber}`, {
        step_number: stepNumber,
        agent_name: agentName,
        prompt_type: promptType,
        prompt,
      })
      .then((response) => response.data.message);
  }

  public moveStep(
    chainName: string,
    oldStepNumber: number,
    newStepNumber: number): Promise<string> {
        return axios
          .patch(`${this.baseUri}/api/chain/${chainName}/step/move`, {
            old_step_number: oldStepNumber,
            new_step_number: newStepNumber,
          })
          .then((response) => response.data.message);
      }
    
      public deleteStep(chainName: string, stepNumber: number): Promise<string> {
        return axios
          .delete(`${this.baseUri}/api/chain/${chainName}/step/${stepNumber}`)
          .then((response) => response.data.message);
      }
        
      public addPrompt(promptName: string, prompt: string): Promise<string> {
        return axios.post(`${this.baseUri}/api/prompt`, { prompt_name: promptName, prompt }).then((response) => response.data.message);
      }
    
      public getPrompt(promptName: string): Promise<any> {
        return axios.get(`${this.baseUri}/api/prompt/${promptName}`).then((response) => response.data.prompt);
      }
    
      public getPrompts(): Promise<string[]> {
        return axios.get(`${this.baseUri}/api/prompt`).then((response) => response.data.prompts);
      }
    
      public getPromptArgs(promptName: string): Promise<any> {
        return axios.get(`${this.baseUri}/api/prompt/${promptName}/args`).then((response) => response.data.prompt_args);
      }
    
      public deletePrompt(promptName: string): Promise<string> {
        return axios.delete(`${this.baseUri}/api/prompt/${promptName}`).then((response) => response.data.message);
      }
    
      public updatePrompt(promptName: string, prompt: string): Promise<string> {
        return axios
          .put(`${this.baseUri}/api/prompt/${promptName}`, { prompt, prompt_name: promptName })
          .then((response) => response.data.message);
      }
    
      public getExtensionSettings(): Promise<any> {
        return axios.get(`${this.baseUri}/api/extensions/settings`).then((response) => response.data.extension_settings);
      }
    
      public getExtensions(): Promise<[string, any][]> {
        return axios.get(`${this.baseUri}/api/extensions`).then((response) => response.data.extensions);
      }
    
      public getCommandArgs(commandName: string): Promise<any> {
        return axios.get(`${this.baseUri}/api/extensions/${commandName}/args`).then((response) => response.data.command_args);
      }
    
      public learnUrl(agentName: string, url: string): Promise<string> {
        return axios
          .post(`${this.baseUri}/api/agent/${agentName}/learn/url`, { url })
          .then((response) => response.data.message);
      }
    
      public learnFile(agentName: string, fileName: string, fileContent: string): Promise<string> {
        return axios
          .post(`${this.baseUri}/api/agent/${agentName}/learn/file`, { file_name: fileName, file_content: fileContent })
          .then((response) => response.data.message);
      }
    }