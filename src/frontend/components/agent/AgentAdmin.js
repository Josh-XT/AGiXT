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
export default function AgentCommandsList({ friendly_name, name, args, enabled }) {
  const agentName = useRouter().query.agent;
  const [newName, setNewName] = useState("");
  const handleDelete = () => {
    axios.delete(`${process.env.API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}`)
      .then(() => mutate(`agents`));
  };
  const handleRename = () => {
    axios.put(`${process.env.API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}`, { new_name: newName })
      .then(() => mutate(`agents`));
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
