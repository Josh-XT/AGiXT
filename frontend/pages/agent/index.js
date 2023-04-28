import axios from 'axios';
import useSWR from 'swr';
import ReactMarkdown from 'react-markdown';
import { Container } from '@mui/material';
import ContentSWR from '@/components/data/ContentSWR';
import DoubleSidedMenu from '@/components/content/PopoutDrawerWrapper';
import MenuAgentList from '@/components/systems/agent/AgentList';
export default function Home() {
  const docs = useSWR('docs/agent', async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/docs/concepts/AGENT.md")).data);
  const agents = useSWR('agent', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent`)).data.agents);
  return <DoubleSidedMenu title={"Agent Homepage"} leftHeading={"Agents"} leftSWR={agents} leftMenu={MenuAgentList} rightHeading={null} rightSWR={null} rightMenu={null} content={() => <Container>
    <ContentSWR swr={docs} content={({ data }) => (
      <ReactMarkdown>{data}</ReactMarkdown>
    )} />;
  </Container>} />;

;
}