
import axios from 'axios';
import { useState } from 'react';
import { Container, TextField, Button, Typography } from '@mui/material';
import { mutate } from "swr"
import useSWR from 'swr';
import DoubleSidedMenu from '@/components/content/DoubleSidedMenu';
import AgentList from '@/components/agent/AgentList';
export default function Home() {
  const [name, setName] = useState("");
  const handleCreate = async () => {
    await axios.post(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/agent`, { agent_name: name });
    mutate("agent");
  }
  const agents = useSWR('agent', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/agent`)).data.agents);
  return <DoubleSidedMenu title={"Add a New Agent"} leftHeading={"Agents"} leftSWR={agents} leftMenu={AgentList} rightHeading={null} rightSWR={null} rightMenu={null} content={() => <Container>
    <Typography variant='h6' component='h2' marginY={"1rem"}>
      Add a New Agent
    </Typography>
   <form>
    <TextField fullWidth variant="outlined" label="Agent Name" value={name} onChange={(e) => {setName(e.target.value)}} />
    <Button variant="contained" color="primary" onClick={handleCreate} sx={{marginY: "1rem"}}>Add a New Agent</Button>
   </form>
  </Container>} />;
}
