import axios from 'axios';
import useSWR from 'swr';
import ReactMarkdown from 'react-markdown';
import { Container } from '@mui/material';
import ContentSWR from '@/components/content/ContentSWR';
import DoubleSidedMenu from '@/components/content/DoubleSidedMenu';
import ChainList from '@/components/chain/ChainList';
export default function Home() {
  const docs = useSWR('docs/prompt', async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/nextjs-2/docs/concepts/CHAIN.md")).data);
  const chains = useSWR('chain', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/chain`)).data);
  return <DoubleSidedMenu title={"Chain Homepage"} leftHeading={"Chains"} leftSWR={chains} leftMenu={ChainList} rightHeading={null} rightSWR={null} rightMenu={null} content={() => <Container>
    <ContentSWR swr={docs} content={({ data }) => (
      <ReactMarkdown>{data}</ReactMarkdown>
    )} />;
  </Container>} />;

;
}