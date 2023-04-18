import React from "react";
import { AppBar, Toolbar, Typography } from "@mui/material";

const AppHeader = () => {
  return (
    <AppBar position="static">
      <Toolbar>
        <Typography variant="h6" component="div">
          Agent-LLM
        </Typography>
      </Toolbar>
    </AppBar>
  );
};

export default AppHeader;