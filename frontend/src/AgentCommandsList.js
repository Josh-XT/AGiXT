import React from 'react';
import { List, ListItem, ListItemButton, Typography } from '@mui/material';

const AgentCommandsList = ({ commands, tabValue, setObjective, setInstruction }) => {
  const handleCommandClick = (command, setText) => {
    setText((prevText) => prevText + command + " for ");
  };

  return (
    <List dense>
      {commands &&
        commands.map((command, index) => (
          <ListItem key={index} disablePadding>
            <ListItemButton
              onClick={() =>
                handleCommandClick(
                  command,
                  tabValue === 0 ? setObjective : setInstruction
                )
              }
            >
              <Typography variant="body2">{command}</Typography>
            </ListItemButton>
          </ListItem>
        ))}
    </List>
  );
};

export default AgentCommandsList;