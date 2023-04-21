import AgentControl from '@/components/agent/AgentControl';
import ContentSWR from '@/components/content/ContentSWR';
import useSWR from 'swr';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { Container } from '@mui/material';
import { useRouter } from 'next/router';
export default function Agent() {
    const agentName = useRouter().query.agent;
    const agent = useSWR(`agent/${agentName}`, async () => (await axios.get(`${process.env.API_URI ?? 'http://localhost:5000'}/api/get_chat_history/${agentName}`)).data);
    return <ContentSWR swr={agent} content={AgentControl} />;
}