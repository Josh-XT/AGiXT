import Link from 'next/link'
import {
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  ListItemIcon,
  Divider
} from "@mui/material";
import {
  RunCircle, 
  StopCircle, 
  AddCircle,
  Home
} from "@mui/icons-material";
import {useRouter} from 'next/router';
export default function MenuPromptList({ data }) {
  const router = useRouter();
  return (
    <List>
      <ListItemButton selected={ router.pathname.split("/")[1]=="prompt"&&!router.query.prompt }>
          <ListItemIcon>
            <Home />
          </ListItemIcon>
          <Link href={`/prompt`}>
            <ListItemText primary="Prompt Homepage" />
          </Link>
        </ListItemButton>
        <ListItemButton disabled selected={  router.pathname.split("/")[1]=="new" && router.pathname.split("/")[2]=="prompt"}>
          <ListItemIcon>
            <AddCircle />
          </ListItemIcon>
          <Link href={`/new/prompt`}>
            <ListItemText primary="Add A New Prompt" />
          </Link>
        </ListItemButton>
      <Divider />
      {data.map((prompt) => (
          <ListItemButton key={prompt} disabled>
            <ListItemIcon>
              {prompt.status ? <RunCircle /> : <StopCircle />}
            </ListItemIcon>
            <Link href={`/prompt/${prompt}`}>
              <ListItemText primary={prompt} />
            </Link>
          </ListItemButton>
      ))}
    </List>
  );
}