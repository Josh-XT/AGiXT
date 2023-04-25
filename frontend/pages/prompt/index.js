import axios from 'axios';
import useSWR from 'swr';
import ReactMarkdown from 'react-markdown';
import { Container } from '@mui/material';
import ContentSWR from '@/components/content/ContentSWR';
import DoubleSidedMenu from '@/components/content/DoubleSidedMenu';
import PromptList from '@/components/prompt/PromptList';
import {useRouter} from 'next/router';
export default function Home() {
  const router = useRouter();
  const docs = useSWR('docs/prompt', async () => (await axios.get("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/docs/nextjs-2/concepts/PROMPT.md")).data);
  const prompts = useSWR('prompt', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/prompt`)).data.prompts);
  return <DoubleSidedMenu title={"Prompt Homepage"} leftHeading={"Prompts"} leftSWR={prompts} leftMenu={PromptList} rightHeading={null} rightSWR={null} rightMenu={null} content={() => <Container>
    <ContentSWR swr={docs} content={({ data }) => (
      <ReactMarkdown>{data}</ReactMarkdown>
    )} />;
  </Container>} />;

;
}