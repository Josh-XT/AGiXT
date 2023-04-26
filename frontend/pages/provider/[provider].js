import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import ContentSWR from '@/components/content/ContentSWR';
import DoubleSidedMenu from '@/components/content/DoubleSidedMenu';
import ProviderList from '@/components/provider/ProviderList';
import { Container } from '@mui/material';
import ReactMarkdown from 'react-markdown';
export default function Provider() {
    const providerName = useRouter().query.provider;
    const docs = useSWR('docs/provider/'+providerName, async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/docs/providers/"+providerName.toUpperCase()+".md")).data);
    const providers = useSWR('provider', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/provider`)).data.providers);
    return <DoubleSidedMenu title={"Provider Homepage"} leftHeading={"Providers"} leftSWR={providers} leftMenu={ProviderList} rightHeading={null} rightSWR={null} rightMenu={null} content={() => <Container>
      <ContentSWR swr={docs} content={({ data }) => (
        <ReactMarkdown>{data}</ReactMarkdown>
      )} />;
    </Container>} />;
  
  
}