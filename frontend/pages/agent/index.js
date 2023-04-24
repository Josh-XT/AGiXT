import axios from 'axios';
import useSWR from 'swr';
import ReactMarkdown from 'react-markdown';
import { Container } from '@mui/material';
import ContentSWR from '@/components/content/ContentSWR';
import DoubleSidedMenu from '@/components/content/DoubleSidedMenu';
import MenuAgentList from '@/components/agent/AgentList';
export default function Home() {
  const docs = useSWR('docs/agent', async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/docs/README.md")).data);
  const agents = useSWR('agents', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/agent`)).data.agents);
  return <DoubleSidedMenu title={"Agent Homepage"} leftHeading={"Agents"} leftSWR={agents} leftMenu={MenuAgentList} rightHeading={null} rightSWR={null} rightMenu={null} content={() => <Container>
    <ContentSWR swr={docs} content={({ data }) => (
      <ReactMarkdown>{data}</ReactMarkdown>
    )} />;
  </Container>} />;

;
}