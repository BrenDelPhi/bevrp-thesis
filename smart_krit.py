from gurobipy import *
from utils import *
from visualizers import visuals
import os
import yaml     # !conda install pyyaml!
import pickle
import argparse


class my_sk():
    def __init__(self, config, out_dir='output'):
        '''
        config: path to YAML or yaml_dict
        '''
        # create output folder and read config
        self.out_dir = out_dir
        if not os.path.exists(self.out_dir):
            os.makedirs(self.out_dir)
        self.time_str = datetime.now().strftime("%m_%d-%H_%M_%S")
        
        if isinstance(config, str):
            with open(config) as config_file:
                yaml_dict = yaml.load(config_file, 
                                    Loader=yaml.FullLoader)
            # base_name = os.path.basename(config)
            # self.instance_name = os.path.splitext(base_name)[0]
        elif isinstance(config, dict):
            yaml_dict = config

        # model settings
        self.obj = yaml_dict['objective']
        self.constr_j = yaml_dict['constr_j']
        self.min_vehicles = yaml_dict['min_vehicles']
        self.limit_vehicles = yaml_dict['limit_vehicles']
        self.visualize = yaml_dict['visualize']
        self.constrain_vehicles = yaml_dict['constrain_vehicles']
        
        # initial settings
        self.t_0 = yaml_dict['t_0']
        self.T = yaml_dict['T']
        self.delta_t = yaml_dict['delta_t']
        self.t_steps = int(self.T / self.delta_t) + 1
        self.times = range(self.t_steps)
        self.c_init = yaml_dict['c_init']
        self.p_init = yaml_dict['p_init']
        self.vehicle_init = yaml_dict['vehicle_init']

        # data sources
        self.vehicle_src = yaml_dict['vehicle_dir']
        self.depot_src = yaml_dict['depot_dir']
        self.consumer_src = yaml_dict['consumer_dir']
        self.producer_src = yaml_dict['producer_dir']
        self.other_src = yaml_dict['other_dir']
        # Data restrictions
        self.v_max = yaml_dict['v_max']
        self.c_max = yaml_dict['c_max']
        self.p_max = yaml_dict['p_max']
        self.o_max = yaml_dict['o_max']
        self.d_max = yaml_dict['d_max']
        self.lat = yaml_dict['lat']
        self.lon = yaml_dict['lon']

        # gurobi settings
        self.threads = yaml_dict['threads']
        self.method = yaml_dict['method']
        self.MIPFocus = yaml_dict['MIPFocus']
        self.MIPGap = yaml_dict['MIPGap']
        self.CutPasses = yaml_dict['CutPasses']
        self.write_lp = yaml_dict['write_lp']
        self.LogToConsole = yaml_dict['LogToConsole']
        self.TimeLimit = yaml_dict['TimeLimit']

        # heuristic settings
        self.h_init_time_limit = yaml_dict['h_init_time_limit']
        self.h_time_limit = yaml_dict['h_time_limit']
        self.h_init = yaml_dict['h_init']

        # read data
        self.get_node_data()
        self.init_nodes()
        self.vehicle_data = get_vehicle_data(yaml_dict)
        self.vehicles = range(self.vehicle_data.shape[0])

        if self.constrain_vehicles is None:
            inter_str = ''
        else:
            inter_str = '{:02d}of'.format(self.constrain_vehicles)
        self.instance_str = '{:02d}c_{:02d}p_{:03d}t_{}{:02d}v'.format(
            len(self.consumers),
            len(self.producers),
            self.t_steps-1,
            inter_str,
            len(self.vehicles)
        )
        if os.path.exists(os.path.join(self.out_dir, 
                                       self.instance_str + '_log.txt')):
            self.instance_str += ('_' + self.time_str)
        self.LogFile = os.path.join(self.out_dir, 
                                    self.instance_str + '_log.txt')

        self.mod = Model("smart_krit")


    def get_node_data(self):
        '''
        Read node_data from the respective files 
        in the specified directories.
        Also omit data outside of the specified lat/lon-ranges.

        Args:
            yaml_dict (dict): Dictionary containing information 
                            from config-file 
        Returns:
            node_data (pd.Dataframe): Dataframe containing 
                                    all relevant node_data.
        '''
        depot_data = get_pd_frame('D', self.depot_src, 
                                  self.d_max, self.lat, self.lon)
        consumer_data = get_pd_frame('C', self.consumer_src, 
                                    self.c_max, self.lat, self.lon)
        producer_data = get_pd_frame('P', self.producer_src,
                                    self.p_max, self.lat, self.lon)
        node_data = pd.concat([depot_data, consumer_data, 
                            producer_data], ignore_index=True)

        # this can be used to only include other nodes within
        # the region defined by all other node types above
        if False:
            if np.min(node_data['lat'].values) > self.lat[0]:
                self.lat[0] = np.min(node_data['lat'].values)
            if np.max(node_data['lat'].values) < self.lat[1]:
                self.lat[1] = np.max(node_data['lat'].values)
            if np.min(node_data['lon'].values) > self.lon[0]:
                self.lon[0] = np.min(node_data['lon'].values)
            if np.max(node_data['lon'].values) < self.lon[1]:
                self.lon[1] = np.max(node_data['lon'].values) 

        other_data = get_pd_frame('O', self.other_src, 
                                  self.o_max, self.lat, self.lon)
        
        self.node_data = pd.concat([node_data, other_data], 
                            ignore_index=True)        


    def init_nodes(self):
        '''
        Initialize node-related data.
        - read available node_data
        - creates model-specific lists and sets for further use.
        '''
        node_data = self.node_data
        depots = node_data.index[node_data['type'] == 'D']
        self.depots = depots.tolist()
        consumers = node_data.index[node_data['type'] == 'C']
        self.consumers = consumers.tolist()
        producers = node_data.index[node_data['type'] == 'P']
        self.producers = producers.tolist()
        self.N_pc = self.consumers + self.producers
        others = node_data.index[node_data['type'] == 'O']
        self.others = others.tolist()
        self.nodes = range(node_data.shape[0])
        self.dist = get_distance(node_data, 'air')
        self.n_names = node_data['ID'].values   
        self.n_type = node_data['type'].values  
        self.n_x = node_data['lon'].values      
        self.n_y = node_data['lat'].values      
        self.profiles = node_data['profile'].values                    
        self.S_n_max = node_data['cap[kWh]'].values     
        self.s_n0 = node_data['cap[kWh]'].values.copy()
        for n in range(len(self.s_n0)):
            if self.n_type[n] == 'D':
                pass
            elif self.n_type[n] == 'P':
                self.s_n0[n] = self.p_init * self.s_n0[n]
            elif self.n_type[n] == 'C':
                self.s_n0[n] = self.c_init * self.s_n0[n]
        self.n_charge = node_data['n_charge'].values            
        self.n_peak = node_data['peak[kW]'].values              
        self.P_n = node_data['power_cdc[kW]'].values
        self.E_nt = get_profiles(self.N_pc, self.n_peak, 
                                 self.profiles, self.t_0, 
                                 self.delta_t, self.t_steps)


    def preprocess(self):
        '''
        Preprocess data for gurobi
        - initialize vehicle-related data
        - sets with index lists for variable creation
        - dictionaries for constraint-formulation
        '''
        log_str = 'Solving problem for: \n{} vehicles'.format(
                    len(self.vehicles))
        log_str += '\n{} consumers\n{} producers'.format(
                    len(self.consumers), len(self.producers))
        log_str += '\n{} depots\n{} other nodes'.format(
                    len(self.depots), len(self.others))
        log_str += '\n{} timesteps with delta = {} h'.format(
                    self.t_steps-1, self.delta_t)
        log_str += '\nobjective: {}'.format(self.obj)
        log_str += '\nC init: {}\nP init: {}'.format(self.c_init, self.p_init)
        log_str += '\nV init: {}\n'.format(self.vehicle_init)

        if self.LogToConsole:
            print(log_str)
        with open(self.LogFile, 'a') as logfile:
            logfile.write(log_str) 

        # vehicles
        self.S_v_max = self.vehicle_data['cap[kWh]'].values 
        if self.vehicle_init in ['None', None]:
            self.s_v0 = self.vehicle_data['cap_0[kWh]'].values
        else:
            self.s_v0 = (self.vehicle_init * 
                         self.vehicle_data['cap[kWh]'].values)
        rental_costs = self.vehicle_data['costs'].values
        P_v = self.vehicle_data['power_cdc[kW]'].values
        v_cons = self.vehicle_data['consumption[kWh/km]'].values            
        self.v_speed = self.vehicle_data['speed[km/h]'].values       
        self.v_names = self.vehicle_data['name'].values

        # sets for better readability
        sets = {}
        sets['vnmt'] = [(v, n, m, t) for v in self.vehicles 
                        for t in self.times for n in self.nodes 
                        for m in self.nodes]
        sets['w'] = [(v, n, m, t) for v in self.vehicles 
                     for t in self.times for n in self.nodes 
                     for m in self.nodes 
                     if self.dist[n,m]/self.v_speed[v] <= 
                     self.delta_t and not 
                     (t==self.times[0] and not n in self.depots)        
                     and not 
                     (t==self.times[-2] and not m in self.depots)       
                     and not 
                     (t==self.times[-1])
                    ]
        if self.LogToConsole:
            print('# w-variables used: {}/{}'.format(
                  len(sets['w']), len(sets['vnmt'])))
        sets['f'] = [(v, n, t) for v in self.vehicles 
                     for n in self.N_pc for t in self.times[1:-2]]
        sets['f_nt'] = [(n, t) for n in self.N_pc 
                        for t in self.times[1:-2]]
        sets['f_vt'] = [(v, t) for v in self.vehicles 
                        for t in self.times[1:-2]]
        sets['s_vt'] = [(v, t) for v in self.vehicles 
                        for t in self.times[1:]]
        sets['s_nt'] = [(n, t) for n in self.N_pc 
                        for t in self.times[1:]]
        sets['e_nt'] = [(n, t) for n in self.producers 
                        for t in self.times]

        self.U_vnm = {}
        self.P_vn = {}
        self.P_vn_signed = {}
        self.lambda_v = {}
        self.depot_dict_0 = {} # vnmt starting from depot n -> 1
        self.depot_dict_N = {} # vnmt ending in depot m -> 1
        self.w_neq = {}        # vnmt with n not equal m
        
        for t in self.times:
            for n in self.N_pc:
                for v in self.vehicles:
                    self.P_vn[v,n,t] = np.min([P_v[v], 
                                       self.P_n[n]]) * self.delta_t
                    if n in self.consumers:
                        self.P_vn_signed[v,n,t] = -self.P_vn[v,n,t]
                    else:
                        self.P_vn_signed[v,n,t] = self.P_vn[v,n,t]
            for v in self.vehicles:
                for n in self.nodes:
                    for m in self.nodes:
                        if n == m:
                            self.w_neq[v,n,m,t] = 0.0
                        else: 
                            self.w_neq[v,n,m,t] = 1.0
                        self.U_vnm[v,n,m,t] = float('{:.2f}'.format
                                     (self.dist[n][m] * v_cons[v]))
                        if n in self.depots:
                            self.depot_dict_0[v,n,m,t] = 1.0
                        else:
                            self.depot_dict_0[v,n,m,t] = 0.0
                        if m in self.depots:
                            self.depot_dict_N[v,n,m,t] = 1.0
                        else:
                            self.depot_dict_N[v,n,m,t] = 0.0
        for v in self.vehicles:
            self.lambda_v[v] = rental_costs[v]

        self.sets = sets


    def solve(self, f_start=None, w_start=None, s_n_start=None, s_v_start=None,
              z_start=None, e_start=None, f_fix=None):
        '''
        Solve the model with Gurobi.

        Args (optional):
            f_start (dict): values to use as warm-start for f_vnt
            w_start (dict): values to use as warm-start for w_vnmt
            s_n_start (dict): values to use as warm-start for s_nt
            s_v_start (dict): values to use as warm-start for s_vt
            f_fix (dict): values to be fixed for f_vnt 

        Returns:
            mod (GRB.Model object): solved gurobi-model
        '''
        sets = self.sets
        mod = self.mod
        mod.remove(mod.getVars())
        mod.remove(mod.getConstrs())

        self.mod.Params.LogFile = self.LogFile
        mod.Params.LogToConsole = self.LogToConsole
        mod.Params.threads = self.threads
        mod.Params.method = self.method
        mod.Params.MIPFocus = self.MIPFocus
        mod.Params.MIPGap = self.MIPGap
        mod.Params.CutPasses = self.CutPasses
        #
        mod.Params.OptimalityTol = 1e-3
        mod.Params.FeasibilityTol = 1e-3
        mod.Params.IntFeasTol = 1e-3
        #
        if not self.TimeLimit is None:
            mod.Params.TimeLimit = self.TimeLimit 

        #############
        # VARIABLES #
        #############
        if self.LogToConsole:
            print('Adding variables...')
        # fraction of charge for vehicle v at producer p 
        # between time t and t+1
        f_vnt = mod.addVars(sets['f'], lb = 0.0, ub = 1.0, 
                            name="f_vnt")
        # transfor of vehicle v from n to m during t to t+1
        w_vnmt = mod.addVars(sets['w'], vtype=GRB.BINARY, 
                             name="w_vnmt")
        # stored energy at each time_step
        s_vt = mod.addVars(sets['s_vt'], lb = 0.0, 
                           ub = [self.S_v_max[v] 
                                 for (v,t) in sets['s_vt']], 
                           name="s_vt")
        s_nt = mod.addVars(sets['s_nt'], lb = 0.0, 
                           ub = [self.S_n_max[n] 
                                 for (n,t) in sets['s_nt']], 
                           name="s_nt")
        e_nt = mod.addVars(sets['e_nt'], 
                           lb = 0.0, name="e_nt")
        # vehicles used (only if required)
        if self.min_vehicles:
            z_v = mod.addVars(self.vehicles, vtype=GRB.BINARY, 
                              name="z_v")

        warm_starts = 0
        # if available: use warm-start
        if not(f_start is None):
            for (v,n,t) in sets['f']:
                try:
                    f_vnt[v,n,t].start = f_start[v,n,t]
                    warm_starts += 1
                except KeyError:
                    pass   
        if not(w_start is None):
            for (v,n,m,t) in sets['w']:
                try: 
                    w_vnmt[v,n,m,t].start = w_start[v,n,m,t]
                    warm_starts += 1
                except KeyError:
                    pass
        if not(s_n_start is None):
            for (n,t) in sets['s_nt']:
                try: 
                    s_nt[n,t].start = s_n_start[n,t]
                    warm_starts += 1
                except KeyError:
                    pass
        if not(s_v_start is None):
            for (v,t) in sets['s_vt']:
                try: 
                    s_vt[v,t].start = s_v_start[v,t]
                    warm_starts += 1
                except KeyError:
                    pass
        if z_start is not None and self.min_vehicles:
            for v in self.vehicles:
                try: 
                    z_v[v].start = z_start[v]
                    warm_starts += 1
                except KeyError:
                    pass
        if e_start is not None:
            for (n,t) in sets['e_nt']:
                try: 
                    e_nt[n,t].start = e_start[n,t]
                    warm_starts += 1
                except KeyError:
                    pass

        print(f'Applied {warm_starts} warmstarts...\n')

        # if available: fix values of f
        if not (f_fix is None):
            f_dict = f_fix[0]
            v_ind = f_fix[1]
            for (v,n,t) in sets['f']:
                try:
                    f_vnt[v,n,t].ub = f_dict[v_ind,n,t]
                    f_vnt[v,n,t].lb = f_dict[v_ind,n,t]
                except KeyError:
                    pass   

        #############
        # OBJECTIVE #
        #############
        if self.obj == 0:
            mod.setObjective(0, GRB.MINIMIZE)
        elif self.obj == 1:
            if self.min_vehicles:
                mod.setObjective(z_v.prod(self.lambda_v,'*') + 
                                 0.31*w_vnmt.prod(self.U_vnm, '*', 
                                                  '*', '*','*') 
                                 + 0.000001 * e_nt.sum('*','*'), 
                                 GRB.MINIMIZE)            
                print('Minimizing vehicle and energy costs...')    
            else:
                mod.setObjective(0.31*w_vnmt.prod(self.U_vnm, '*', 
                                                  '*', '*','*')
                                 + 0.000001 * e_nt.sum('*','*'), 
                                 GRB.MINIMIZE)
        else: 
            exit('unknown objective_id, exiting...')

        ###############
        # CONSTRAINTS #
        ###############
        if self.LogToConsole:      
            print('Adding constraints...')

        
        if self.constrain_vehicles is not None:
            mod.addConstr(z_v.sum('*') <= self.constrain_vehicles)
        

        # each vehicle can only be located 
        # at one node at each timestep
        mod.addConstrs((w_vnmt.sum(v, '*', '*', t) == 1) 
                       for v in self.vehicles 
                       for t in self.times[1:-2])

        # vehicles start in depot
        mod.addConstrs((w_vnmt.prod(self.depot_dict_0, v, '*', '*', 
                                    self.times[0]) == 1) 
                        for v in self.vehicles)

        # vehicles end in depot
        mod.addConstrs((w_vnmt.prod(self.depot_dict_N,v, '*', '*',
                                    self.times[-2]) == 1) 
                        for v in self.vehicles)
        
        # connectivity constraints
        mod.addConstrs((w_vnmt.sum(v, '*', n, t) == 
                        w_vnmt.sum(v, n, '*', t+1)) 
                       for v in self.vehicles for n in self.nodes 
                       for t in self.times[:-2])
        
        # capacity updates producers:
        mod.addConstrs((s_nt[n, 1] == self.s_n0[n] 
                        + self.E_nt[n, 0] 
                        - f_vnt.prod(self.P_vn,'*', n, 0) 
                        - e_nt[n, 0]) for n in self.producers)
        mod.addConstrs((s_nt[n, t+1] == s_nt[n, t] 
                        + self.E_nt[n, t] 
                        - f_vnt.prod(self.P_vn,'*', n, t) 
                        - e_nt[n, t]) for n in self.producers 
                        for t in self.times[1:-1])

        # capacity updates consumers:
        if f_fix is None:
            mod.addConstrs((s_nt[n, 1] == self.s_n0[n] 
                            - self.E_nt[n, 0] 
                            + f_vnt.prod(self.P_vn,'*', n, 0)) 
                            for n in self.consumers)
            mod.addConstrs((s_nt[n, t+1] == s_nt[n, t] 
                            - self.E_nt[n, t] 
                            + f_vnt.prod(self.P_vn,'*', n, t)) 
                            for n in self.consumers 
                            for t in self.times[1:-1])

        # capacity updates vehicles:
        mod.addConstrs((s_vt[v, 1] == self.s_v0[v] 
                        + f_vnt.prod(self.P_vn_signed, v, '*', 0) 
                        - w_vnmt.prod(self.U_vnm, v, '*','*', 0)) 
                        for v in self.vehicles)                                              
        mod.addConstrs((s_vt[v, t+1] == s_vt[v, t] 
                        + f_vnt.prod(self.P_vn_signed, v, '*', t) 
                        - w_vnmt.prod(self.U_vnm, v, '*','*', t)) 
                        for v in self.vehicles 
                        for t in self.times[1:-1])

        # (dis)charge only if vehicle was present at that location (before and after charging)
        mod.addConstrs((f_vnt[v, n, t] <= w_vnmt[v, n, n, t]) 
                       for (v, n, t) in sets['f'])
        # optional: if vehicle is on the move, 
        # no (dis-)charging anywhere
        if self.constr_j:
            mod.addConstrs((w_vnmt.prod(self.w_neq,v,'*','*',t) 
                            <= 1 - f_vnt.sum(v,'*',t)) 
                            for (v,t) in sets['f_vt'])
        # count only vehicles that (dis-)charged
        M_j = self.t_steps
        if self.min_vehicles:
            mod.addConstrs((f_vnt.sum(v,'*','*') <= M_j * z_v[v]) 
                           for v in self.vehicles)
        if self.limit_vehicles:
            mod.addConstrs((f_vnt.sum('*', n, t) <= 
                            self.n_charge[n]) 
                            for (n, t) in sets['f_nt'])
        if self.write_lp:
            mod.write('model.lp')

        # Optimize model
        mod.optimize()
        if mod.status == 2: 
            mod.printQuality()

        return mod


    def postprocess(self, mod):
        '''
        Write solution to output files, 
        call visualization routine if desired.
        
        Args:
            mod (GUROBI.Model): solved gurobi-model
        '''        
        if hasattr(mod, 'objVal'):
            pass
            #print('Obj: %g' % mod.objVal)
        else: 
            print('infeasible!')
            exit()

        # save, plot, etc.
        filepath = os.path.join(self.out_dir, self.instance_str + '.txt')

        varlist = mod.getVars()
        with open(filepath, 'w') as out_file:
            for v in varlist:
                if hasattr(v, 'x'):
                    out_file.write( '%s %g' % (v.varName, v.x) )
                    out_file.write('\n')

        model_dict = {'times': self.times,
                       't_0': self.t_0,                
                       'delta_t': self.delta_t,
                       't_steps': self.t_steps,
                       'nodes': self.nodes,
                       'n_names': self.n_names,
                       'n_type': self.n_type,
                       'n_x': self.n_x,
                       'n_y': self.n_y,
                       'n_peak': self.n_peak,
                       'S_n_max': self.S_n_max,
                       's_n0': self.s_n0,
                       'vehicles': self.vehicles,
                       'v_names': self.v_names,
                       'S_v_max': self.S_v_max,
                       's_v0': self.s_v0,
                       'P_vn': self.P_vn,
                       'E_nt': self.E_nt,
                        }
        pickle_path = os.path.join(self.out_dir, self.instance_str + '.p')
        with open(pickle_path, 'wb') as p_path:
            pickle.dump(model_dict, p_path)

        if self.visualize:
            my_vis = visuals(model_dict, filepath)
            my_vis.time_series_plots()
            my_vis.interactive_plot()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
                        description='Visualize a specific file.')
    parser.add_argument('-c', '--config', 
                        dest='config', default='config.yaml', 
                        help='Config file to be used')
    parser.add_argument('-w', '--warmstart', 
                        dest='warmstart', default=None, 
                        help='File for warm-start results')
    args = parser.parse_args()

    # solve model with parsed config-file 
    sk = my_sk(args.config)
    sk.preprocess()
    if args.warmstart is None:
        grb_mod = sk.solve()
    else:
        if os.path.exists(args.warmstart):
            w, s_n, s_v, f, z, e = read_results(args.warmstart)
            grb_mod = sk.solve(w_start=w, s_n_start=s_n, s_v_start=s_v,
                               f_start=f, z_start=z, e_start=e)
        else:
            exit(f'warmstart-file {args.warmstart} does not exist!')

    sk.postprocess(grb_mod)
