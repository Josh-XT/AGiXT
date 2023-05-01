import { useState, useEffect } from "react";
import { useRouter } from "next/router";
import axios from "axios";
import useSWR from "swr";
import { mutate } from "swr"
import {
  TextField,
  Button,
  Divider,
  Container,
  Slider,
  Box,
  MenuItem,
  Select,
  Typography
} from "@mui/material";
export default function AgentAdmin({ friendly_name, name, args, enabled }) {
  const agentName = useRouter().query.agent;
  const [newName, setNewName] = useState("");
  const [provider, setProvider] = useState("");
  const [fields, setFields] = useState([]);
  const [fieldValues, setFieldValues] = useState({});
  const providers = useSWR('provider', async () => (await axios.get(`/api/provider`)).data);
  const agentConfig = useSWR(`agent/${agentName}`, async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}`)).data);
  const fieldComponents = {
    "MODEL_PATH": <TextField key={"MODEL_PATH"} label="Model Path" sx={{my: "1rem", mx: "0.5rem" }} value={fieldValues.MODEL_PATH} onChange={(e) => setFieldValues({...fieldValues, MODEL_PATH: e.target.value})} />,
    "MAX_TOKENS": <Box key={"MAX_TOKENS"} sx={{my: "1rem", display: "flex", alignItems: "center"}}><Slider min={32} max={8192} sx={{mr: "1rem"}} value={fieldValues.MAX_TOKENS} onChange={(e) => setFieldValues({...fieldValues, MAX_TOKENS: e.target.value})} /><TextField label="Maximum Tokens" value={fieldValues.MAX_TOKENS} onChange={(e) => setFieldValues({...fieldValues, MAX_TOKENS: e.target.value})} /></Box>,
    "AI_TEMPERATURE": <Box key={"AI_TEMPERATURE"} sx={{my: "1rem",display: "flex", alignItems: "center"}}><Slider min={0.1} max={1} step={0.1} sx={{mr: "1rem"}} value={fieldValues.AI_TEMPERATURE} onChange={(e) => setFieldValues({...fieldValues, AI_TEMPERATURE: e.target.value})} /><TextField label="AI Temperature" value={fieldValues.AI_TEMPERATURE} onChange={(e) => setFieldValues({...fieldValues, AI_TEMPERATURE: e.target.value})} /></Box>,
  };
  
  const handleConfigure = async () => {
    await axios.put(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}`, { new_name: newName })
    mutate(`agent`);
  };
  useEffect(() => {
    if (agentConfig.data?.agent?.settings?.provider) setProvider(agentConfig.data.agent.settings.provider);
  }, [agentConfig.data]);
  useEffect(() => {
    setFields([]);
    async function getAndSetFields() {
      setFields((await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/provider/${provider}`)).data.settings);
    }
    getAndSetFields();
  }, [provider]);
  console.log(agentConfig);
  return (
    <Container>
        <Typography variant="h6" sx={{my: "1rem"}}>Agent Provider</Typography>
        <Select label="Provider" sx={{ mx: "0.5rem" }} value={provider} onChange={(e) => setProvider(e.target.value)}>
            <MenuItem value={""}>Select a Provider...</MenuItem>
            {providers.data?Object.keys(providers.data).map((provider) => {
                return <MenuItem key={provider} value={provider}>{providers.data[provider]}</MenuItem>;
            }):null}
        </Select>
        <Typography variant="h6" sx={{my: "1rem"}}>Provider Settings</Typography>
        {fields?.map((field) => 
          fieldComponents[field]
        )}
         <Button onClick={handleConfigure} variant="contained" color="error">Save Agent Configuration</Button>
    </Container>
  );
};
