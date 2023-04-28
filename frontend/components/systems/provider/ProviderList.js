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
  Home,
  SmartToy
} from "@mui/icons-material";
import { useRouter } from 'next/router';
export default function ProviderList({ data }) {
  const router = useRouter();
  const providerMap = {
    "bard": "Bard",
    "chatgpt": "ChatGPT",
    "fastchat": "FastChat",
    "huggingchat": "HuggingChat",
    "kobold": "Kobold",
    "llamacpp": "LlamaCPP",
    "oobabooga": "OobaBooga",
    "openai"  : "OpenAI"
  }
  return (
    <List>
      <ListItemButton selected={ router.pathname.split("/")[1]=="provider"&&!router.query.provider }>
          <ListItemIcon>
            <Home />
          </ListItemIcon>
          <Link href={`/provider`}>
            <ListItemText primary="Provider Homepage" />
          </Link>
        </ListItemButton>
      <Divider />
      {data.map((provider) => (
          <ListItemButton key={provider} selected={router.query.provider==provider}>
            <ListItemIcon>
              <SmartToy />
            </ListItemIcon>
            <Link href={`/provider/${provider}`}>
              <ListItemText primary={providerMap[provider]} />
            </Link>
          </ListItemButton>
      ))}
    </List>
  );
}