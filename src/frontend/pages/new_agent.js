
import axios from 'axios';
import { useState } from 'react';
import { Container, TextField, Button, Typography } from '@mui/material';

export default function Home() {
  const [name, setName] = useState("");
  const handleCreate = () => {
    axios.post(`${process.env.API_URI ?? 'http://localhost:5000'}/api/agent`, { agent_name: name })
  }
  return <Container>
    <Typography variant='h6' component='h2' marginY={"1rem"}>
      Create an Agent
    </Typography>
   <form>
    <TextField fullWidth variant="outlined" label="Agent Name" value={name} onChange={(e) => {setName(e.target.value)}} />
    <Button variant="contained" color="primary" onClick={handleCreate} sx={{marginY: "1rem"}}>Create Agent</Button>
   </form>
  </Container>;
}