import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import ContentSWR from '@/components/content/ContentSWR';
import PromptControl from '@/components/prompt/PromptControl';
export default function Agent() {
    const promptName = useRouter().query.prompt;
    const prompt = useSWR(`prompt/${promptName}`, async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/prompt/${promptName}`)).data);
    return <ContentSWR swr={prompt} content={PromptControl} />;
}