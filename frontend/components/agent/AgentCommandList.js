import {
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  ListItemIcon,
  Typography,
  Switch,
  Divider
} from "@mui/material";
import AgentCommand from "./AgentCommand";
import { mutate } from "swr";
import axios from "axios";
import { useRouter } from "next/router";

export default function AgentCommandList({data}) {
  const agentName = useRouter().query.agent;

  const handleToggleAllCommands = () => {
      axios.post(`${process.env.API_URI ?? 'http://localhost:5000'}/api/${data.every((command) => command.enabled) ? "disable" : "enable"}_all_commands/${agentName}`).then(() => mutate(`agent/${agentName}/commands`));
  }
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
              onChange={handleToggleAllCommands}
              inputProps={{ "aria-label": "Enable/Disable All Commands" }}
            />
          </ListItem>
    <Divider />
      {data.map((command) =>  (
            <AgentCommand key={command.name} {...command} />
      ))}

    </List>
  );
}