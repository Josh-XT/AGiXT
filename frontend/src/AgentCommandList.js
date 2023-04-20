import { useState, useContext, useEffect } from "react";
import {
  List,
  ListItem,
  ListItemButton,
  Typography,
  Switch
} from "@mui/material";
import { URIContext } from "./App";
import AgentCommand from "./AgentCommand";

const AgentCommandsList = ({ agent }) => {
  const baseURI = useContext(URIContext);
  const [allToggled, setAllToggled] = useState(false);
  const [allCommands, setAllCommands] = useState({friendly_name: "All Commands", name: "all", enabled: allToggled, args: {}});
  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    updateCommands();
  }, []);
  useEffect(() => {
    setAllToggled(commands.every((command) => command.enabled));
    setLoading(false);
  }, [commands]);
  useEffect(() => {
    setAllCommands({...allCommands, enabled: allToggled});
  }, [allToggled])

  const updateCommands = async () => {
    try {
      const commands = await (await fetch(`${baseURI}/api/get_commands/${agent}`)).json();
      console.log(commands);
      setCommands([...commands.commands.sort()]);
    } catch (error) {
      console.error("Error Fetching Commands:\n", error);
      setCommands([]);
    }
  }

  console.log(commands);
  return (
    loading ? <></> :
    <List dense>
      {[allCommands, ...commands].map((command) => (
        <AgentCommand key={command.name} {...command} agent={agent} refresh={updateCommands}/>
        ))}
    </List>
  );
};

export default AgentCommandsList;