
import axios from 'axios';
import { useState } from 'react';
import { Container, TextField, Button, Typography } from '@mui/material';
import { mutate } from "swr"
import useSWR from 'swr';
import PopoutDrawerWrapper from '../../components/menu/PopoutDrawerWrapper';
import AgentList from '../../components/systems/agent/AgentList';
export default function Home() {
  const [name, setName] = useState("");
  const handleCreate = async () => {
    await axios.post(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent`, { agent_name: name, settings: { provider: "huggingchat" } });
    mutate("agent");
  }
  const agents = useSWR('agent', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent`)).data.agents);
  return <PopoutDrawerWrapper title={"Add a New Agent"} leftHeading={"Agents"} leftSWR={agents} leftMenu={AgentList} rightHeading={null} rightSWR={null} rightMenu={null} ><Container>
    <Typography variant='h6' component='h2' marginY={"1rem"}>
      Add a New Agent
    </Typography>
   <form>
    <TextField fullWidth variant="outlined" label="Agent Name" value={name} onChange={(e) => {setName(e.target.value)}} />
    <Button variant="contained" color="primary" onClick={handleCreate} sx={{marginY: "1rem"}}>Add a New Agent</Button>
   </form>
  </Container></PopoutDrawerWrapper>
}
