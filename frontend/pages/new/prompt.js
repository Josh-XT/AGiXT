
import axios from 'axios';
import { useState } from 'react';
import { Container, TextField, Button, Typography } from '@mui/material';
import { mutate } from "swr"
import useSWR from 'swr';
import DoubleSidedMenu from '@/components/content/PopoutDrawerWrapper';
import PromptList from '@/components/systems/prompt/PromptList';
export default function Home() {
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const handleCreate = async () => {
    await axios.post(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/prompt`, { prompt_name: name, prompt: prompt });
    mutate("prompt");
  }
  const prompts = useSWR('prompt', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/prompt`)).data.prompts);
  return <DoubleSidedMenu title={"Add a New Prompt"} leftHeading={"Prompts"} leftSWR={prompts} leftMenu={PromptList} rightHeading={null} rightSWR={null} rightMenu={null} content={() => <Container>
    <Typography variant='h6' component='h2' marginY={"1rem"}>
      Add a New Prompt
    </Typography>
   <form>
    <TextField fullWidth variant="outlined" label="Prompt Name" value={name} onChange={(e) => {setName(e.target.value)}} />
    <TextField fullWidth variant="outlined" label="Prompt Body" multiline rows={50} value={prompt} onChange={(e) => {setPrompt(e.target.value)}} />
    <Button variant="contained" color="primary" onClick={handleCreate} sx={{marginY: "1rem"}}>Add a New Prompt</Button>
   </form>
  </Container>} />;
}
