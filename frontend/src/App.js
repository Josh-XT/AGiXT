import React, { useState, useEffect, useCallback } from "react";
import { Container, Box, Grid, Typography } from "@mui/material";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import AgentList from "./AgentList";
import AgentHome from "./AgentHome";
import Agent from "./Agent";
import AppHeader from "./AppHeader";
import './App.css';

const themeGenerator = (darkMode) =>
  createTheme({
    palette: {
      mode: darkMode ? "dark" : "light",
      primary: {
        main: "#273043",
      },

    },
  });


export const URIContext = React.createContext('');
function App() {
  const [darkMode, setDarkMode] = useState(false);
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState("Home");
  const [baseURI, setBaseURI] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const theme = themeGenerator(darkMode);
  async function validateAPI() {
    let uri;
    try {
      if ((await fetch("http://localhost:5000/api/docs")).ok) {
        uri = "http://localhost:5000";
      }
    } catch (error) {
      console.error("Local API server is not accessible:", error);
      console.warn("The API address will be left empty and the service cannot be used.");
      uri = undefined;
      setError(true);
    }
    return uri;
  }

  const loadAgents = () => {
    fetch(`${baseURI}/api/get_agents`).then(agents => agents.json()).then((agents) => setAgents([{name: "Home"}, ...agents.agents]));
  }
  useEffect(() => {
    setLoading(true);
    validateAPI().then((uri) => {
      setBaseURI(uri);
    });
  }, []);
  useEffect(() => {
    try {
      loadAgents();
    }
    catch (error) {
      console.error("Error Fetching Agents:", error);
    }
  }, [baseURI]);
  useEffect(() => {
    if (!agents) setError(true);
    setLoading(false);
  }, [agents]);
  const handleToggleDarkMode = useCallback(() => {
    setDarkMode((old) => !old);
  }, []);
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
        <URIContext.Provider value={baseURI}>
          <AppHeader
            darkMode={darkMode}
            handleToggleDarkMode={handleToggleDarkMode}
          />
            {!Object.values(loading).every(loadingValue => !loadingValue) ?
              <Typography variant="h1" component="h1" align="center">Loading...</Typography> :
              (error ?
                <Typography variant="h1" component="h1" align="center">Error!</Typography> :

                  <Grid container spacing={2}>
                    <AgentList
                      agents={agents}
                      selectedAgent={selectedAgent}
                      setSelectedAgent={setSelectedAgent}
                      loadAgents={loadAgents}
                    />
                    {selectedAgent === "Home" ? <AgentHome /> : <Agent agent={selectedAgent} reloadAgents={loadAgents} />}

                    
                    {/*agents.slice(1).map((agent) =>
                      <Agent key={agent.name} hidden={agent.name !== selectedAgent} agent={agent.name} />
              )*/}
                    
                  </Grid>
   
              )}
        </URIContext.Provider>
    </ThemeProvider>
  );
}

export default App;