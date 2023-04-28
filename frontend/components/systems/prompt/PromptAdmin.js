import { useState } from "react";
import  useSWR  from "swr";
import { useRouter } from "next/router";
import axios from "axios";
import { mutate } from "swr"
import {
  TextField,
  Button,
  Divider,
  Container
} from "@mui/material";
export default function PromptAdmin({ friendly_name, name, args, enabled }) {
  const promptName = useRouter().query.prompt;
  const prompt = useSWR('prompt/'+promptName, async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/prompt/${promptName}`)).data);
  const [newName, setNewName] = useState(prompt.data.prompt_name);
  const [newBody, setNewBody] = useState(prompt.data.prompt);
  console.log(prompt);
  const handleDelete = async () => {
    await axios.delete(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/prompt/${promptName}`)
    mutate(`prompts`);
  };
  const handleSave = async () => {
    await axios.put(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/prompt/${promptName}`, { prompt_name: newName, prompt: newBody })
    mutate(`prompts`);
  };
  return (
    <Container>
      <TextField fullWidth variant="outlined" label="New Prompt Name" value={newName} onChange={(e) => { setNewName(e.target.value) }} />
      <TextField fullWidth multiline rows={30} variant="outlined" label="New Prompt Body" value={newBody} onChange={(e) => { setNewBody(e.target.value) }} />
      <Button variant="contained" color="primary" onClick={handleSave} sx={{ marginY: "1rem" }}>Save Prompt</Button>
      <Divider sx={{my: "1.5rem"}}/>
      <Button onClick={handleDelete} variant="contained" color="error">Delete Prompt</Button>
    </Container>
  );
};
