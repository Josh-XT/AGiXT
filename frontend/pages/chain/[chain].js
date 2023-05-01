import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import ContentSWR from '../../components/data/ContentSWR';
import ChainControl from '../../components/systems/chain/ChainControl';
export default function Chain() {
    const chainName = useRouter().query.chain;
    const chains = useSWR('chain', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain`)).data);
    return <ContentSWR swr={chains} content={ChainControl} />;
}