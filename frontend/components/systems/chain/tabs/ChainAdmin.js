import { useState } from "react";
import { useRouter } from "next/router";
import axios from "axios";
import { mutate } from "swr"
import {
  TextField,
  Button,
  Divider,
  Container
} from "@mui/material";
export default function ChainAdmin({ friendly_name, name, args, enabled }) {
  const router = useRouter();
  const chainName = router.query.chain;
  const [newName, setNewName] = useState("");
  const handleDelete = async () => {
    await axios.delete(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain/${chainName}`)
    mutate(`chain`);
    router.push(`/chain`);
  };
  const handleRename = async () => {
    await axios.put(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain/${chainName}`, { new_name: newName })
    mutate(`chain`);
    router.push(`/chain/${newName}`);
  };
  const handleRun = async () => {
    await axios.post(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain/${chainName}`)
  };
  return (
    <Container>
      <TextField fullWidth variant="outlined" label="New Chain Name" value={newName} onChange={(e) => { setNewName(e.target.value) }} />
      <Button variant="contained" color="primary" onClick={handleRename} sx={{ marginY: "1rem" }}>Rename Chain</Button>
      <Divider sx={{my: "1.5rem"}}/>
      <Button onClick={handleRun} variant="contained" color="success" sx={{mr: "1rem"}}>Run Chain</Button>
      <Button onClick={handleDelete} variant="contained" color="error">Delete Chain</Button>
    </Container>
  );
};
