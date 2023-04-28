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
  InsertComment,
  AddComment,
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
        <ListItemButton selected={  router.pathname.split("/")[1]=="new" && router.pathname.split("/")[2]=="prompt"}>
          <ListItemIcon>
            <AddComment />
          </ListItemIcon>
          <Link href={`/new/prompt`}>
            <ListItemText primary="Add A New Prompt" />
          </Link>
        </ListItemButton>
      <Divider />
      {data.map((prompt) => (
          <ListItemButton key={prompt}>
            <ListItemIcon>
              <InsertComment />
            </ListItemIcon>
            <Link href={`/prompt/${prompt}`}>
              <ListItemText primary={prompt} />
            </Link>
          </ListItemButton>
      ))}
    </List>
  );
}