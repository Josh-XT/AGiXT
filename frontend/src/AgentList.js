import React from "react";
import {
  List,
  ListItem,
  ListItemText,
  IconButton,
  Typography,
  ListItemIcon,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";

const AgentList = ({ agents, selectedAgent, setSelectedAgent }) => {
  const handleAddAgent = (agent_name) => {
    fetch("http://127.0.0.1:5000/api/add_agent", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ agent_name: agent_name }),
    });
  };

  const handleDeleteAgent = (agent_name) => {
    fetch("http://127.0.0.1:5000/api/delete_agent/" + agent_name, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });
  };

  return (
    <>
      <Typography variant="h6" gutterBottom>
        Agents
      </Typography>
      <List>
        {agents.map((agent, index) => (
          <ListItem
            button
            key={index}
            onClick={() => setSelectedAgent(agent)}
            selected={selectedAgent === agent}
          >
            <ListItemText primary={agent} />
            <IconButton
              edge="end"
              aria-label="delete"
              onClick={() => handleDeleteAgent(agent)}
            >
              <DeleteIcon />
            </IconButton>
          </ListItem>
        ))}
        <ListItem button onClick={handleAddAgent}>
          <ListItemIcon>
            <AddIcon />
          </ListItemIcon>
          <ListItemText primary="Add Agent" />
        </ListItem>
      </List>
    </>
  );
};

export default AgentList;