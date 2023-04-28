import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import ChainPanel from '../chain/ChainPanel';
import PopoutDrawerWrapper from '../../menu/PopoutDrawerWrapper';
import ChainList from './ChainList';
export default function ChainControl({ data }) {
    const chainName = useRouter().query.chain;
    const chains = useSWR('chain', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain`)).data);
    return <PopoutDrawerWrapper title={"Manage Chain \""+chainName+"\""} leftHeading={"Chains"} leftSWR={chains} leftMenu={ChainList} rightHeading={null} rightSWR={null} rightMenu={null}>
        <ChainPanel />
    </PopoutDrawerWrapper>;
}


