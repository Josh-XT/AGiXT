import ContentSWR from '@/components/content/ContentSWR';
import useSWR from 'swr';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { Container } from '@mui/material';
export default function Home() {
  const readme = useSWR('readme', async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/README.md")).data);
  console.log(readme);
  return <Container>
  <ContentSWR swr={readme} content={({data}) => (
    <ReactMarkdown>{data}</ReactMarkdown>
  )} />;
  </Container>;
}