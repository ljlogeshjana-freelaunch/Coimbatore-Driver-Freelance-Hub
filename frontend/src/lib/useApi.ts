import { useState } from 'react';
import { api } from './api';
export function useApi<T>(path:string, refreshKey=0){const [data,setData]=useState<T|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);useState(()=>{let mounted=true;api<T>(path).then(value=>{if(mounted)setData(value)}).catch(e=>{if(mounted)setError(e.message)}).finally(()=>{if(mounted)setLoading(false)});return()=>{mounted=false}});return{data,error,loading,setData}}
