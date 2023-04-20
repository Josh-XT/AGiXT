import { useState, useContext } from "react";
import {
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  IconButton,
  Typography,
  ListItemIcon,
  TextField,
  Grid
} from "@mui/material";
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import { URIContext } from "./App";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import DoNotDisturbIcon from '@mui/icons-material/DoNotDisturb';
import RunCircleIcon from '@mui/icons-material/RunCircle';
const AgentList = ({ agents, loadAgents, selectedAgent, setSelectedAgent }) => {
  const [newAgentName, setNewAgentName] = useState("");
  const baseURI = useContext(URIContext);
  const [editing, setEditing] = useState(false);
  const [editingTarget, setEditingTarget] = useState(null);
  const [editingText, setEditingText] = useState("");
  const handleAddAgentClick = () => {
    handleAddAgent(newAgentName);
    setNewAgentName("");
  };
  const handleKeyPress = async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleAddAgentClick();
    }
  };

  const handleAddAgent = (newAgentName) => {
    if (newAgentName.trim() !== "") {
      try {
        fetch(`${baseURI}/api/add_agent/${newAgentName}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
        }).then(() => {
          loadAgents();
        });

      } catch (error) {
        console.error("Error Adding Agent:", error);
      }
    }
  };
  const handleEditCancel = () => {
    setEditing(false);
    setEditingTarget(null);
    setEditingText("");
  }

  const handleEditAgent = (agent) => {
    if (!editing) {
      setEditing(true);
      setEditingTarget(agent);
      setEditingText(agent);
    }
    else {
      try {
        fetch(`${baseURI}/api/rename_agent/${agent}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: {
            "new_name": editingText
          }
        }).then(() => {
          loadAgents();
        });
      } catch (error) {
        console.error("Error Renaming Agent:", error);
      }
      setEditing(false);
      setEditingTarget(null);
      setEditingText("");
    }
  };
  const handleDeleteAgent = (agent) => {
    try {
      fetch(`${baseURI}/api/delete_agent/${agent}`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
        },
      }).then(() => {
        loadAgents();
      });
    } catch (error) {
      console.error("Error Deleting Agent:", error);
    }
  };

  return (
    <Grid item xs={3}>
      <Typography variant="h6" gutterBottom>
        Agents
      </Typography>
      <List>
        {agents.map((agent) => (
          <ListItemButton
            key={agent.name}
            onClick={() => setSelectedAgent(agent.name)}
            selected={selectedAgent === agent.name}
          >
            {editing && editingTarget === agent.name ?
              <TextField
                label={`Rename ${agent.name}`}
                value={editingText}
                onChange={(e) => setEditingText(e.target.value)}
              /> : <ListItemText primary={agent.name} />
            }

            {agent.status ? <RunCircleIcon /> : null}
            {agent.name !== "Home" ?
              <>
                {editing && editingTarget != agent.name ? null :
                  <IconButton
                    edge="end"
                    aria-label="delete"
                    onClick={() => handleEditAgent(agent.name)}
                  >
                    {editing && editingTarget == agent.name ? <SaveIcon /> : <EditIcon />}
                  </IconButton>
                }
                <IconButton
                  edge="end"
                  aria-label="delete"
                  onClick={() => editing && editingTarget ? handleEditCancel() : handleDeleteAgent(agent.name)}
                >
                  {editing && editingTarget == agent.name ? <DoNotDisturbIcon /> : <DeleteIcon />}
                </IconButton>
              </>
              : null}
          </ListItemButton>
        ))}
        <ListItem>
          <TextField
            label="New Agent Name"
            value={newAgentName}
            onChange={(e) => setNewAgentName(e.target.value)}
            onKeyPress={handleKeyPress}
          />
          <ListItemIcon>
            <IconButton
              aria-label="add"
              onClick={handleAddAgentClick}
              disabled={newAgentName.trim() === ""}
            >
              <AddIcon />
            </IconButton>
          </ListItemIcon>
        </ListItem>
      </List>
    </Grid>
  );
};

export default AgentList;
