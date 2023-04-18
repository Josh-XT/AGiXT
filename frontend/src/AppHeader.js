import React from "react";
import {
  AppBar,
  Toolbar,
  Typography,
  FormGroup,
  FormControlLabel,
  Switch,
} from "@mui/material";

const AppHeader = ({ darkMode, handleToggleDarkMode }) => {
  const handleClick = (e) => {
    e.stopPropagation();
  };

  return (
    <AppBar position="static">
      <Toolbar>
        <Typography variant="h6" component="div">
          Agent-LLM
        </Typography>
        <div style={{ marginLeft: "auto" }}>
          <FormGroup>
            <FormControlLabel
              control={
                <Switch checked={darkMode} onChange={handleToggleDarkMode} />
              }
              label="Toggle Dark Mode"
              onClick={handleClick}
            />
          </FormGroup>
        </div>
      </Toolbar>
    </AppBar>
  );
};

export default AppHeader;