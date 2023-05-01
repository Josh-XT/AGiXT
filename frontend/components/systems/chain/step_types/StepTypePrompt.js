import { Select, MenuItem, TextField } from "@mui/material";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/router";
import axios from "axios";
import { mutate } from "swr";
import useSWR from "swr";
export default function StepTypePrompt({agent_name, set_agent_name, prompt_name, set_prompt_name, prompt, set_prompt, update}) {
    const [agent, setAgent] = useState(-1);
    const [promptNameVal, setPromptNameVal] = useState(-1);
    const [promptText, setPromptText] = useState("");
    const agents = useSWR('agent', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent`)).data.agents);
    const prompts = useSWR('prompt', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/prompt`)).data.prompts);
    useEffect(() => {
        setPromptText(prompt);
    }, [prompt]);
    useEffect(() => {
        setPromptNameVal(prompts.data&&prompt_name?prompts.data.findIndex((prompt) => prompt.name == prompt_name):-1);
    }, [prompts.data, prompt_name]);
    useEffect(() => {
        setAgent(agents.data&&agent_name?agents.data.findIndex((agent) => agent.name == agent_name):-1);
    }, [agents.data, agent_name]);
    console.log(prompts.data);
    return <>
        <Select label="Type" sx={{ mx: "0.5rem" }} value={agent} onChange={(e) => {setAgent(e.target.value); if (e.target.value != -1) set_agent_name(agents.data[e.target.value].name);update(true);}}>
            <MenuItem value={-1}>Select an Agent...</MenuItem>
            {agents?.data?.map((agent, index) => {
                return <MenuItem key={index} value={index}>{agent.name}</MenuItem>;
            })}
        </Select>

        <Select label="Prompt" sx={{ mx: "0.5rem" }} value={promptNameVal} onChange={(e) => {setPromptNameVal(e.target.value); if (e.target.value != -1 && e.target.value != -2) set_prompt_name(prompts.data[e.target.value].name);update(true);}}>
            <MenuItem value={-1}>Select a Prompt...</MenuItem>
            <MenuItem value={-2}>[New Prompt]</MenuItem>
            {prompts?.data?.map((prompt, index) => {
                return <MenuItem key={index} value={index}>{prompt}</MenuItem>;
            })}
        </Select>

        {promptNameVal===-2?<TextField label="New Prompt" value={promptText} onChange={(e) => {setPromptText(e.target.value); set_prompt(e.target.value);update(true);}} multiline lines={20} sx={{ mx: "0.5rem", flex: 1 }} />:null}
    </>;
}