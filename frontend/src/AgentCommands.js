import React, { useState } from "react";
import {
  List,
  ListItem,
  ListItemButton,
  Typography,
  Switch
} from "@mui/material";
import { URIContext } from "./App";

const AgentCommandsList = ({ agent }) => {
  const baseURI = useContext(URIContext);
  const [allToggled, setAllToggled] = useState(false);
  const [commands, setCommands] = useState([]);

  useEffect(async () => {
    updateCommands();
  }, []);
  useEffect(() => {
    setAllToggled(commands.every((command) => command.enabled));
  }, [commands]);

  const updateCommands = async () => {
    try {
      setCommands(await (await fetch(`${baseURI}/api/get_commands/${agent}`)).json());
    } catch (error) {
      console.error("Error Fetching Commands:\n", error);
    }
  }
  const handleToggleCommand = async (command) => {
    const endpoint = command === "All Commands" ?
      `${baseURI}/api/${enabled ? "disable" : "enable"}_all_commands/${agent}`:
      `${baseURI}/api/${enabled ? "disable" : "enable"}_command/${agent}/${command}`;

    fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }).then(() => updateCommands());
  };


  return (
    <List dense>
      {commands &&
        commands.unshift({ command: "All Commands", enabled: allToggled }).map((command) => (
          <ListItem key={command} disablePadding onClick={() => handleToggleCommand(command)}>
            <ListItemButton>
              <Typography variant="body2">
                {command}
              </Typography>
            </ListItemButton>
            <Switch
              checked={enabledCommands[command]}
              inputProps={{ "aria-label": "Enable/Disable Command" }}
            />
          </ListItem>
        ))}
    </List>
  );
};

export default AgentCommandsList;