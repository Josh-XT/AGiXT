import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import ContentSWR from '@/components/content/ContentSWR';
import ChainControl from '@/components/chain/ChainControl';
export default function Chain() {
    const chainName = useRouter().query.chain;
    const chain = useSWR(`chain/${chainName}`, async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain/${chainName}`)).data);
    return <ContentSWR swr={chain} content={ChainControl} />;
}