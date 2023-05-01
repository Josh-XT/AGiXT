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
export default function AgentAdmin({ friendly_name, name, args, enabled }) {
  const router = useRouter();
  const agentName = router.query.agent;
  const [newName, setNewName] = useState("");
  const handleDelete = async () => {
    await axios.delete(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}`)
    mutate(`agent`);
    router.push(`/agent`);
  };
  const handleRename = async () => {
    // TODO: Get agentName out of URI as it makes a 404 upon success.
    await axios.patch(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}`, { old_name: agentName, new_name: newName })
    mutate(`agent`);
    router.push(`/agent/${newName}`);
  };
  return (
    <Container>
      <TextField fullWidth variant="outlined" label="New Agent Name" value={newName} onChange={(e) => { setNewName(e.target.value) }} />
      <Button variant="contained" color="primary" onClick={handleRename} sx={{ marginY: "1rem" }}>Rename Agent</Button>
      <Divider sx={{my: "1.5rem"}}/>
      <Button onClick={handleDelete} variant="contained" color="error">Delete Agent</Button>
    </Container>
  );
};
