import React, { useState, useEffect } from "react";
import { Container, Box, Grid } from "@mui/material";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import AgentList from "./AgentList";
import AgentControls from "./AgentControls";
import AppHeader from "./AppHeader";

function App() {
  const [darkMode, setDarkMode] = useState(false);
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);

  useEffect(() => {
    const fetchAgents = async () => {
      const response = await fetch("http://127.0.0.1:5000/api/get_agents");
      const data = await response.json();
      setAgents(data.agents);
      setSelectedAgent(data.agents[0]);
    };

    fetchAgents();
  }, []);

  const theme = createTheme({
    palette: {
      mode: darkMode ? "dark" : "light",
      primary: {
        main: "#3f51b5",
      },
    },
  });

  const handleToggleDarkMode = () => {
    setDarkMode(!darkMode);
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppHeader />
      <Container maxWidth="lg">
        <Box sx={{ my: 4, display: "flex" }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={4}>
              <AgentList
                agents={agents}
                selectedAgent={selectedAgent}
                setSelectedAgent={setSelectedAgent}
              />
            </Grid>
            <Grid item xs={12} sm={8}>
              <AgentControls
                darkMode={darkMode}
                handleToggleDarkMode={handleToggleDarkMode}
                selectedAgent={selectedAgent}
              />
            </Grid>
          </Grid>
        </Box>
      </Container>
    </ThemeProvider>
  );
}

export default App;