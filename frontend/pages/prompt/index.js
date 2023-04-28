import axios from 'axios';
import useSWR from 'swr';
import ReactMarkdown from 'react-markdown';
import { Container } from '@mui/material';
import ContentSWR from '@/components/data/ContentSWR';
import DoubleSidedMenu from '@/components/content/PopoutDrawerWrapper';
import PromptList from '@/components/systems/prompt/PromptList';
import {useRouter} from 'next/router';
export default function Home() {
  const router = useRouter();
  const docs = useSWR('docs/prompt', async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/docs/main/concepts/PROMPT.md")).data);
  const prompts = useSWR('prompt', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/prompt`)).data.prompts);
  return <DoubleSidedMenu title={"Prompt Homepage"} leftHeading={"Prompts"} leftSWR={prompts} leftMenu={PromptList} rightHeading={null} rightSWR={null} rightMenu={null} content={() => <Container>
    <ContentSWR swr={docs} content={({ data }) => (
      <ReactMarkdown>{data}</ReactMarkdown>
    )} />;
  </Container>} />;

;
}