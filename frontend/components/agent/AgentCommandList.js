import { useRouter } from "next/router";
import axios from "axios";
import { mutate } from "swr";
import {
  List,
  ListItem,
  ListItemButton,
  Typography,
  Switch,
  Divider
} from "@mui/material";
import AgentCommand from "./AgentCommand";
export default function AgentCommandList({ data }) {
  const agentName = useRouter().query.agent;
  const handleToggleAllCommands = async () => {
    await axios.patch(`${process.env.API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/command`, { command_name: "*", enable: data.every((command) => command.enabled) ? "false" : "true" });
    mutate(`agent/${agentName}/commands`);
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
      {data.map((command, index) => (
        <AgentCommand key={index} {...command} />
      ))}

    </List>
  );
}