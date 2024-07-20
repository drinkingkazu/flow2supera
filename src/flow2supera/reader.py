import h5py 
import h5flow
import numpy as np
from ROOT import supera
from yaml import Loader
import yaml
import os
import flow2supera


class InputEvent:
    event_id = -1
    true_event_id = -1
    segments = None
    hit_indices = None
    hits = None
    backtracked_hits = None
    calib_final_hits  = None
    trajectories = None
    interactions = []
    t0 = -1
    segment_index_min = -1
    event_separator = ''


class InputReader:
    
    def __init__(self, parser_run_config, input_files=None,config=None):
        self._input_files = input_files
        if not isinstance(input_files, str):
            raise TypeError('Input file must be a str type')
        self._event_ids = None
        self._event_t0s = None
        self._flash_t0s = None
        self._flash_ids = None
        self._event_hit_indices = None
        self._hits = None
        self._backtracked_hits = None
        self._segments = None
        self._trajectories = None
        self._interactions = None
        self._run_config = parser_run_config
        self._is_sim = False
        self._is_mpvmpr= False
        if config:
            if os.path.isfile(config):
                file=config
            else:
               file=flow2supera.config.get_config(config)
            with open(file,'r') as f:
                cfg=yaml.load(f.read(),Loader=Loader)
                if 'SimulationType' in cfg.keys():
                    self._is_mpvmpr=cfg.get('SimulationType')=='mpvmpr'
                
        
        if input_files:
            self.ReadFile(input_files)

    def __len__(self):
        if self._event_ids is None: return 0
        return len(self._event_ids)

    
    def __iter__(self):
        for entry in range(len(self)):
            yield self.GetEvent(entry)

    def ReadFile(self, input_files, verbose=False):

        print('Reading input file...')

        # H5Flow's H5FlowDataManager class associated datasets through references
        # These paths help us get the correct associations
        events_path            = 'charge/events/'
        events_data_path       = 'charge/events/data/'
        event_hit_indices_path = 'charge/events/ref/charge/calib_prompt_hits/ref_region/'
        packets_path           = 'charge/packets'
        calib_final_hits_path  = 'charge/calib_final_hits/data'
        calib_prompt_hits_path = 'charge/calib_prompt_hits/data'
        backtracked_hits_path  = 'mc_truth/calib_prompt_hit_backtrack/data'
        interactions_path      = 'mc_truth/interactions/data'
        segments_path          = 'mc_truth/segments/data'
        trajectories_path      = 'mc_truth/trajectories/data'

        self._is_sim = False 
        # TODO Currently only reading one input file at a time. Is it 
        # necessary to read multiple? If so, how to handle non-unique
        # event IDs?
        #for f in input_files:
        flow_manager = h5flow.data.H5FlowDataManager(input_files, 'r')
        with h5py.File(input_files, 'r') as fin:
            events = flow_manager[events_path]
            events_data = events['data']
            self._event_ids = events_data['id']
            #ts_start is in ticks and 0.1 microseconds per tick for charge readout
            self._event_t0s = events_data['unix_ts'] + events_data['ts_start']/1e7 
            self._event_hit_indices = flow_manager[event_hit_indices_path]
            self._hits              = flow_manager[calib_prompt_hits_path]
            self._backtracked_hits  = flow_manager[backtracked_hits_path]
            self._is_sim = 'mc_truth' in fin.keys()
            if self._is_sim:
                #self._segments = flow_manager[events_path,
                #                              calib_final_hits_path,
                #                              calib_prompt_hits_path,
                #                              packets_path,
                #                              segments_path]
                self._segments     = np.array(flow_manager[segments_path])
                self._trajectories = np.array(flow_manager[trajectories_path])
                self._interactions = np.array(flow_manager[interactions_path])

        # This next bit is only necessary if reading multiple files
        # Stack datasets so that there's a "file index" preceding the event index
        #self._event_ids = np.stack(event_ids)
        #self._event_ids = np.concatenate(event_ids)
        #self._event_t0s = np.stack(t0s)
        #self._calib_final_hits = np.stack(calib_final_hits)
        #self._t0s = np.stack(t0s)
        #self._segments = np.stack(segments)
        #self._trajectories = np.stack(trajectories)

        if not self._is_sim:
            print('Currently only simulation is supoprted')
            raise NotImplementedError
    
    def GetNeutrinoIxn(self, ixn, ixn_idx):
        
        nu_result = supera.Neutrino()

        if isinstance(ixn,np.void):
            return nu_result
        
        nu_result.id = int(ixn_idx)
        nu_result.interaction_id = int(ixn['vertex_id']) 
        nu_result.target = int(ixn['target'])
        nu_result.vtx = supera.Vertex(ixn['x_vert'], ixn['y_vert'], ixn['z_vert'], ixn['t_vert'])
        # nu_result.vtx = supera.Vertex(ixn['vertex'][0], ixn['vertex'][1], ixn['vertex'][2], ixn['vertex'][3])
        nu_result.pdg_code = int(ixn['nu_pdg'])
        nu_result.lepton_pdg_code = int(ixn['lep_pdg'])  
        nu_result.energy_init = ixn['Enu']
        nu_result.theta = ixn['lep_ang']
        nu_result.momentum_transfer =  ixn['Q2']
        nu_result.momentum_transfer_mag =  ixn['q3']
        nu_result.energy_transfer =  ixn['q0']
        nu_result.bjorken_x = ixn['x']
        nu_result.inelasticity = ixn['y']
        nu_result.px = ixn['nu_4mom'][0]
        nu_result.py = ixn['nu_4mom'][1]       
        nu_result.pz = ixn['nu_4mom'][2]
        nu_result.lepton_p = ixn['lep_mom']
        if(ixn['isCC']): nu_result.current_type = 0
        else: nu_result.current_type = 1
        nu_result.interaction_mode = int(ixn['reaction'])
        nu_result.interaction_type = int(ixn['reaction'])   
        
        return nu_result  
        
    # To truth associations go as hits -> segments -> trajectories


    def GetEventIDFromSegments(self, backtracked_hits, segments):

        
        try:
            seg_ids = np.concatenate([bhit['segment_ids'][bhit['fraction']!=0.] for bhit in backtracked_hits])

            mask = [i for i in range(len(segments)) if segments[i]['segment_id'] in seg_ids]

            #return np.unique(segments[seg_ids]['event_id'])
            return np.unique(segments[mask]['event_id'])

        except ValueError:
            valid_frac_counts = [(bhit['fraction']!=0.).sum() for bhit in backtracked_hits]
            if sum(valid_frac_counts) > 0:
                # case the original error was not due to empty association, re-raise
                raise
            print(f'[SuperaDriver] UNEXPECTED: found no hit with any association to the truth hit')
            return np.array([])


    def EntryQualityCheck(self, entry):
        
        # this entry
        hidx_min, hidx_max = self._event_hit_indices[entry]
        bhits = self._backtracked_hits[hidx_min:hidx_max]
        ids_this = self.GetEventIDFromSegments(bhits,self._segments)
        if not len(ids_this) == 1:
            print(f'[SuperaDriver] ERROR: this entry {entry} contains multiple event_id values {ids_this}')
            return np.array([])

        # previous entry if entry>0
        if entry > 0:
            hidx_min, hidx_max = self._event_hit_indices[entry-1]
            bhits = self._backtracked_hits[hidx_min:hidx_max]
            ids_prev = self.GetEventIDFromSegments(bhits,self._segments)
            if ids_this[0] in ids_prev:
                print(f'[SuperaDriver] ERROR: this entry {entry} with event id {ids_this[0]} has some hits mixed into the previous entry {entry-1}')
                return np.array([])

        if entry+1 < len(self._event_ids):
            hidx_min, hidx_max = self._event_hit_indices[entry+1]
            bhits = self._backtracked_hits[hidx_min:hidx_max]
            ids_next = self.GetEventIDFromSegments(bhits,self._segments)
            if ids_this[0] in ids_next:
                print(f'[SuperaDriver] ERROR: this entry {entry} with event id {ids_this[0]} has some hits mixed into the next entry {entry+1}')
                return np.array([])

        return ids_this


    def GetEntry(self, entry):
        
        if entry >= len(self._event_ids):
            print('Entry {} is above allowed entry index ({})'.format(entry, len(self._event_ids)))
            print('Invalid read request (returning None)')
            return None
        
        result = InputEvent()

        result.event_id = self._event_ids[entry]

        result.t0 = self._event_t0s[entry] 

        result.hit_indices = self._event_hit_indices[entry]
        hidx_min, hidx_max = self._event_hit_indices[entry]
        result.hits = self._hits[hidx_min:hidx_max]
        result.backtracked_hits = self._backtracked_hits[hidx_min:hidx_max]

        #st_event_id = self.GetEventIDFromSegments(result.backtracked_hits,self._segments)
        st_event_id = self.EntryQualityCheck(entry)

        if len(st_event_id) < 1:
            print(f'[SuperaDriver] Skipping this entry ({entry})...')
            return result

        assert len(st_event_id)==1, f'Found >1 unique "event_id" from backtracked segments ({st_event_id})'

        st_event_id = st_event_id[0]

        result.segments = self._segments[self._segments['event_id']==st_event_id]
        result.trajectories = self._trajectories[self._trajectories['event_id']==st_event_id]


        result.interactions = []
        if len(result.segments) != 0:
            result.true_event_id = st_event_id
            interactions_array  = np.array(self._interactions)
            event_interactions = interactions_array[interactions_array['event_id'] == result.true_event_id]
            if not self._is_mpvmpr:
                for ixn_idx, ixn in enumerate(event_interactions):
                    supera_nu = self.GetNeutrinoIxn(ixn, ixn_idx)
                    result.interactions.append(supera_nu)
            
        return result
 


    def EventDump(self, input_event):
        print('-----------EVENT DUMP-----------------')
        print('Event ID {}'.format(input_event.event_id))
        print('True event ID {}'.format(input_event.true_event_id))
        print('Event t0 {}'.format(input_event.t0))
        print('Event hit indices (start, stop):', input_event.hit_indices)
        print('Backtracked hits len:', len(input_event.backtracked_hits))
        print('Reconstructed hits len:', len(input_event.hits))
        print('segments in this event:', len(input_event.segments))
        print('trajectories in this event:', len(input_event.trajectories))
        print('interactions in this event:', len(input_event.interactions))



