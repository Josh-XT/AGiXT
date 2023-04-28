import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import ContentSWR from '@/components/data/ContentSWR';
import PopoutDrawerWrapper from '../../components/menu/PopoutDrawerWrapper';
import ProviderList from '../../components/systems/provider/ProviderList';
import { Container } from '@mui/material';
import ReactMarkdown from 'react-markdown';
export default function Provider() {
  const providerName = useRouter().query.provider;
  const docs = useSWR('docs/provider/' + providerName, async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/docs/providers/" + providerName.toUpperCase() + ".md")).data);
  const providers = useSWR('provider', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/provider`)).data.providers);
  return <PopoutDrawerWrapper title={"Provider Homepage"} leftHeading={"Providers"} leftSWR={providers} leftMenu={ProviderList} rightHeading={null} rightSWR={null} rightMenu={null} >

    <Container>
      <ContentSWR swr={docs} content={({ data }) => (
        <ReactMarkdown>{data}</ReactMarkdown>
      )} />;
    </Container></PopoutDrawerWrapper>;


}