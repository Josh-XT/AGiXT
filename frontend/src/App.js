import React, { useState, useEffect, useCallback } from "react";
import { Container, Box, Grid } from "@mui/material";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import AgentList from "./AgentList";
import AgentControls from "./AgentControls";
import AppHeader from "./AppHeader";

const themeGenerator = (darkMode) =>
  createTheme({
    palette: {
      mode: darkMode ? "dark" : "light",
      primary: {
        main: "#3f51b5",
      },
    },
  });

  function App() {
    const [darkMode, setDarkMode] = useState(false);
    const [agents, setAgents] = useState([]);
    const [selectedAgent, setSelectedAgent] = useState(null);
    const [loading, setLoading] = useState(false);
    const [baseURI, setBaseURI] = useState("");
  
    async function getBaseURI() {
      try {
        const response = await fetch("http://127.0.0.1:5000");
        if (response.ok) {
          return "http://127.0.0.1:5000";
        }
      } catch (error) {
        console.warn("Local endpoint not accessible:", error);
      }
      return "";
    }
  
    useEffect(() => {
      async function setURI() {
        setBaseURI(await getBaseURI());
      }
      setURI();
    }, []);
  
    const fetchAgents = useCallback(async () => {
      setLoading(true);
      try {
        const response = await fetch(`${baseURI}/api/get_agents`);
        const data = await response.json();
        setAgents(data.agents);
        setSelectedAgent(data.agents[0]);
      } catch (error) {
        console.error("Error fetching agents:", error);
      }
      setLoading(false);
    }, [baseURI]);
  
    useEffect(() => {
      fetchAgents();
    }, [fetchAgents]);  

  const handleToggleDarkMode = useCallback(() => {
    setDarkMode((prevDarkMode) => !prevDarkMode);
  }, []);

  const handleAddAgent = async (newAgentName) => {
    if (newAgentName.trim() !== "") {
      setLoading(true);
      try {
        await fetch(`${baseURI}/api/add_agent/` + newAgentName, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
        });
        fetchAgents();
      } catch (error) {
        console.error("Error adding agent:", error);
      }
      setLoading(false);
    }
  };

  const handleDeleteAgent = async (agent_name) => {
    setLoading(true);
    try {
      await fetch(`${baseURI}/api/delete_agent/` + agent_name, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
        },
      });
      fetchAgents();
    } catch (error) {
      console.error("Error deleting agent:", error);
    }
    setLoading(false);
  };

  const theme = themeGenerator(darkMode);

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
                handleAddAgent={handleAddAgent}
                handleDeleteAgent={handleDeleteAgent}
                loading={loading}
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
