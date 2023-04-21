import {
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  ListItemIcon
} from "@mui/material";
import { 
  RunCircle, StopCircle 
} from "@mui/icons-material";
import Link from 'next/link'

export default function MenuAgentList({data}) {

  return (
    <List>
      {data.map((agent) => (
        <ListItem key={agent.name} disablePadding>
          <ListItemButton>
            <ListItemIcon>
              {agent.running ? <RunCircle /> : <StopCircle />}
            </ListItemIcon>
            <Link href={`/agents/${agent.name}`}>
              <ListItemText primary={agent.name} />
            </Link>
          </ListItemButton>
        </ListItem>
      ))}
    </List>
  );
}