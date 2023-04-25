import axios from 'axios';
import useSWR from 'swr';
import ReactMarkdown from 'react-markdown';
import { Container } from '@mui/material';
import ContentSWR from '@/components/content/ContentSWR';
import DoubleSidedMenu from '@/components/content/DoubleSidedMenu';
import ProviderList from '@/components/provider/ProviderList';
export default function Home() {
  const docs = useSWR('docs/prompt', async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/docs/concepts/PROVIDER.md")).data);
  const providers = useSWR('provider', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/provider`)).data.providers);
  return <DoubleSidedMenu title={"Provider Homepage"} leftHeading={"Providers"} leftSWR={providers} leftMenu={ProviderList} rightHeading={null} rightSWR={null} rightMenu={null} content={() => <Container>
    <ContentSWR swr={docs} content={({ data }) => (
      <ReactMarkdown>{data}</ReactMarkdown>
    )} />;
  </Container>} />;

;
}