import {
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  ListItemIcon,
  Typography,
  Switch,
  Separator
} from "@mui/material";
import { 
  RunCircle, StopCircle 
} from "@mui/icons-material";
import Link from 'next/link'

export default function AgentCommandList({data}) {
  const toggleAllCommands = () => {

  }
  console.log(data);
  return (
    <List dense>
      <ListItem disablePadding >
            <ListItemButton>
              <Typography variant="body2">
                All Commands
              </Typography>
            </ListItemButton>
            <Switch
              checked={data.every((command) => command.enabled)}
              onChange={toggleAllCommands}
              inputProps={{ "aria-label": "Enable/Disable All Commands" }}
            />
          </ListItem>
          <Separator />
      {/*data.map((commands) => (
          {[allCommands, ...commands].map((command) => (
            <AgentCommand key={command.name} {...command} agent={agent} refresh={updateCommands}/>
            ))}
          ))*/}
    </List>
  );
}