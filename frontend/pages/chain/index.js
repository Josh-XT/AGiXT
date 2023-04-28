import axios from 'axios';
import useSWR from 'swr';
import ReactMarkdown from 'react-markdown';
import { Container } from '@mui/material';
import ContentSWR from '../../components/data/ContentSWR';
import PopoutDrawerWrapper from '../../components/menu/PopoutDrawerWrapper';
import ChainList from '../../components/systems/chain/ChainList';
export default function Home() {
  const docs = useSWR('docs/chain', async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/docs/concepts/CHAIN.md")).data);
  const chains = useSWR('chain', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain`)).data);
  return <PopoutDrawerWrapper title={"Chain Homepage"} leftHeading={"Chains"} leftSWR={chains} leftMenu={ChainList} rightHeading={null} rightSWR={null} rightMenu={null} ><Container>
    <ContentSWR swr={docs} content={({ data }) => (
      <ReactMarkdown>{data}</ReactMarkdown>
    )} />;
  </Container></PopoutDrawerWrapper>;
}