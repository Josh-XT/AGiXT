import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import ContentSWR from '@/components/data/ContentSWR';
import PromptControl from '@/components/systems/prompt/PromptControl';
export default function Prompt() {
    const promptName = useRouter().query.prompt;
    const prompt = useSWR(`prompt/${promptName}`, async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/prompt/${promptName}`)).data);
    return <ContentSWR swr={prompt} content={PromptControl} />;
}