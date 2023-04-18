import React, { useState, useEffect } from 'react';
import {
  AppBar,
  Box,
  Button,
  Container,
  CssBaseline,
  TextField,
  Toolbar,
  Typography,
  Paper,
  Switch,
  FormGroup,
  FormControlLabel,
  List,
  ListItem,
  ListItemText,
  IconButton,
  Grid,
  ListItemIcon,
} from '@mui/material';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';

const TaskList = () => (
  <Typography variant="subtitle1" gutterBottom>
    TASK LIST
  </Typography>
);

const NextTask = ({ task }) => (
  <Typography variant="subtitle2" gutterBottom>
    NEXT TASK: {task.task_id}: {task.task_name}
  </Typography>
);

const Result = ({ result }) => (
  <Typography variant="body1" gutterBottom>
    {result}
  </Typography>
);

function App() {
  const [darkMode, setDarkMode] = useState(false);
  const [objective, setObjective] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);

  useEffect(() => {
    // Fetch the agents list from the backend
    const fetchAgents = async () => {
      // Replace with the appropriate API endpoint to fetch agents
      const response = await fetch('http://127.0.0.1:5000/api/get_agents');
      const data = await response.json();
      setAgents(data.agents);
      setSelectedAgent(data.agents[0]);
    };

    fetchAgents();
  }, []);

  const theme = createTheme({
    palette: {
      mode: darkMode ? 'dark' : 'light',
      primary: {
        main: '#3f51b5',
      },
    },
  });

  const handleToggleDarkMode = () => {
    setDarkMode(!darkMode);
  };

  const handleAddAgent = () => {
    // Add code to create a new agent and update the list of agents
  };

  const handleDeleteAgent = (agent) => {
    // Add code to delete the selected agent and update the list of agents
  };

  // Implement the run function to call your Flask API endpoints here
  const run = async () => {
    // Set the objective
    await fetch('http://127.0.0.1:5000/api/set_objective', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ objective }),
    });
  
    while (true) {
      // Execute the next task
      const response = await fetch('http://127.0.0.1:5000/api/execute_next_task');
      const data = await response.json();
  
      if (!data.task || !data.result) {
        setChatHistory((prevChatHistory) => [
          ...prevChatHistory,
          '*****ALL TASKS COMPLETE*****',
        ]);
        break;
      }
  
      setChatHistory((prevChatHistory) => [
        ...prevChatHistory,
        `*****TASK LIST*****\n${data.task_list.map((task, index) => `${index + 1}. ${task.task_name}`).join('\n')}`,
        `*****NEXT TASK*****\n${data.task.task_id}: ${data.task.task_name}`,
        `*****RESULT*****\n${data.result}`,
      ]);    
  
      await new Promise((resolve) => setTimeout(resolve, 1000)); // Sleep for 1 second
    }
  };
  
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="div">
            Agent-LLM
          </Typography>
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg">
        <Box sx={{ my: 4, display: 'flex' }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={4}>
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
            </Grid>
            <Grid item xs={12} sm={8}>
              <FormGroup>
                <FormControlLabel
                  control={<Switch checked={darkMode} onChange={handleToggleDarkMode} />}
                  label="Toggle Dark Mode"
                />
              </FormGroup>
              <TextField
                fullWidth
                label="Enter Objective"
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                sx={{ mb: 2 }}
              />
              <Button variant="contained" color="primary" onClick={run} fullWidth>
                Start Agent-LLM
              </Button>
              <Box mt={2} p={2} bgcolor={theme.palette.background.paper} borderRadius={1}>
                <Typography variant="h6" gutterBottom>
                  Chat History
                </Typography>
                <Paper
                  elevation={3}
                  style={{ padding: '16px', maxHeight: '300px', overflowY: 'auto' }}
                >
                  {chatHistory.map((message, index) => {
                    if (message === '*****TASK LIST*****') {
                      return <TaskList key={index} />;
                    } else if (message.startsWith('*****NEXT TASK*****')) {
                      const taskId = message.split(':')[1]?.trim();
                      const taskName = message.split(':')[2]?.trim();
                      const task = {
                        task_id: taskId,
                        task_name: taskName,
                      };
                      return <NextTask key={index} task={task} />;
                    } else if (message.startsWith('*****RESULT*****')) {
                      return <Result key={index} result={message.split(': ')[1]} />;
                    } else {
                      return (
                        <Typography key={index} gutterBottom>
                          {message}
                        </Typography>
                      );
                    }
                  })}
                </Paper>
              </Box>
            </Grid>
          </Grid>
        </Box>
      </Container>
    </ThemeProvider>
  );
}

export default App;
