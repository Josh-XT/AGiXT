import React, { useState } from "react";
import {
  List,
  ListItem,
  ListItemButton,
  Typography,
  Switch,
  FormControlLabel,
} from "@mui/material";

const AgentCommandsList = ({
  commands,
  tabValue,
  setObjective,
  setInstruction,
  handleToggleCommand,
  handleToggleAllCommands,
  enabledCommands,
  selectedAgent,
  baseURI,
}) => {
  const [allToggled, setAllToggled] = useState(false);

  const handleCommandClick = (command, setText) => {
    setText((prevText) => prevText + command + " for ");
  };

  const handleAllToggled = async () => {
    setAllToggled(!allToggled);
    await handleToggleAllCommands(!allToggled, selectedAgent, baseURI);
  };

  const handleToggleCommandClick = async (command) => {
    await handleToggleCommand(
      command,
      selectedAgent,
      enabledCommands[command],
      baseURI
    );
  };
  return (
    <>
      <FormControlLabel
        control={
          <Switch
            checked={allToggled}
            onChange={handleAllToggled}
            name="allToggled"
          />
        }
        label={allToggled ? "Disable All" : "Enable All"}
      />
      <List dense>
        {commands &&
          commands.map((command, index) => (
            <ListItem key={index} disablePadding>
              <ListItemButton>
                <Typography
                  variant="body2"
                  onClick={() =>
                    handleCommandClick(
                      command,
                      tabValue === 0 ? setObjective : setInstruction
                    )
                  }
                >
                  {command}
                </Typography>
              </ListItemButton>
              <Switch
                checked={enabledCommands[command]}
                onChange={() => handleToggleCommandClick(command)}
                inputProps={{ "aria-label": "Enable/Disable Command" }}
              />
            </ListItem>
          ))}
      </List>
    </>
  );
};

export default AgentCommandsList;