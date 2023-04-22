import axios from 'axios';
import useSWR from 'swr';
import ReactMarkdown from 'react-markdown';
import { Container } from '@mui/material';
import ContentSWR from '@/components/content/ContentSWR';
export default function Home() {
  const readme = useSWR('readme', async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/README.md")).data);
  console.log(readme);
  return <Container>
    <ContentSWR swr={readme} content={({ data }) => (
      <ReactMarkdown>{data}</ReactMarkdown>
    )} />;
  </Container>;
}