import os
import sys
import do_json
import raas_utils
import hyp_utils
import constants
import ipaddress
#import logging
#from logging import info as raas_utils.log_service
#logging.basicConfig(filename='raas.log', filemode='a', format='%(asctime)s %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

"""@params:
    param1 = l2_transit config file (required)
"""

if __name__=="__main__":
    if (len(sys.argv) < 2):
        raas_utils.log_service("Please give l2_transit config file")
        raas_utils.log_client("Please give l2_transit config file")
        exit(1)

    l2_transit_config_file = sys.argv[1]

    l2_transit_name = l2_transit_config_file.split('/')[-1].split('.')[0]

    #Assumed customer always gives correct config file
    l2_transit_data = do_json.json_read(l2_transit_config_file)

    hypervisor = l2_transit_data["hypervisor_name"]
    hypervisor_arg = "hypervisor="+hypervisor

    hypervisors_data = hyp_utils.get_hypervisors_data()

    hypervisor_ip = hyp_utils.get_hyp_ip(hypervisor)

    if raas_utils.client_exists_l2_transit(l2_transit_name):
        raas_utils.client_service("l2_transit already exists "+ l2_transit_name)
        raas_utils.log_service("l2_transit already exists "+ l2_transit_name)
        exit(1)
    
    #All prereq checks done at this point
    l2_transit_capacity = l2_transit_data["capacity"]
    l2_transit_name = l2_transit_data["l2_transit_name"]
    self_as = str(l2_transit_data["self_as"])

    if l2_transit_capacity == "f1":
        vcpu = "1,1"
        mem = "1G"
    elif l2_transit_capacity == "f2":
        vcpu = "1,2"
        mem = "2G"
    elif l2_transit_capacity == "f3":
        vcpu = "1,3"
        mem = "4G"
    else:
        raas_utils.log_client("Unknown flavor using default")
        raas_utils.log_service("Unknown flavor using default")
        vcpu = "1,1"
        mem = "1G"
    
    cid = hyp_utils.get_client_id()

    try:
        #create transit
        try:
            l2id = hyp_utils.get_l2_transit_id(hypervisor)
            l2_transit_name_ansible = "c"+ str(cid) + "_" + "l2t" + str(l2id)
            l2_transit_name_ansible_arg = "c_name="+l2_transit_name_ansible

            t_ram_arg = "c_ram=" + str(mem)
            t_vcpu_arg = "c_vcpu=" + str(vcpu)

            extra_vars = constants.ansible_become_pass + " " + \
                    t_ram_arg + " " + t_vcpu_arg + " " + \
                    l2_transit_name_ansible_arg + " " + \
                    hypervisor_arg

            #raas_utils.log_service("ansible-playbook logic/misc/create_container.yml -i logic/inventory/hosts.yml -v --extra-vars '"+extra_vars+"'")
            rc = raas_utils.run_playbook("ansible-playbook logic/misc/create_router_container.yml -i logic/inventory/hosts.yml -v --extra-vars '"+extra_vars+"'")
            if (rc != 0):
                raise

            hyp_utils.write_l2_transit_id(l2id+1, hypervisor)
            hyp_utils.hyp_add_l2_transit(hypervisor, l2_transit_name, l2_transit_name_ansible)
            raas_utils.client_add_l2_transit(hypervisor, l2_transit_name, l2_transit_capacity, self_as)
            
        except Exception as e:
            raas_utils.log_client("create l2_transit failed")
            raas_utils.log_service("create l2_transit failed deleting transit"+ str(e))
            raas_utils.run_playbook("ansible-playbook logic/misc/delete_container.yml -i logic/inventory/hosts.yml -v --extra-vars '"+extra_vars+"'")
            raise

        #configure transit
        try:
            t_name_arg = "t_name="+l2_transit_name_ansible

            t_loopback_ip = raas_utils.get_new_veth_subnet('loopbacks')
            t_loopback_ip_arg = "t_loopback_ip="+str(t_loopback_ip)

            network=raas_utils.get_new_veth_subnet('l2t_h')
            subnet = network.split('/')

            t_h_ip = str(ipaddress.ip_address(subnet[0])+1) + '/' + subnet[1]
            t_h_ip_arg = "t_h_ip="+t_h_ip

            h_t_ip = str(ipaddress.ip_address(subnet[0])+2) + '/' + subnet[1]
            h_t_ip_arg = "h_t_ip="+h_t_ip

            c_hyp_id = l2_transit_name_ansible.split('_')[0]
            t_hyp_id = l2_transit_name_ansible.split('_')[1]

            ve_t_h_arg = "ve_t_h=" + c_hyp_id + '_ve_' + t_hyp_id + '_h'
            ve_h_t_arg = "ve_h_t=" + c_hyp_id + '_ve_h_' + t_hyp_id 

            extra_vars = constants.ansible_become_pass + " "\
                     + t_name_arg + " " + t_loopback_ip_arg + \
                    " "  +  hypervisor_arg + \
                    " " + t_h_ip_arg + " " + h_t_ip_arg + " " + \
                    " " + ve_t_h_arg + " " + ve_h_t_arg

            #raas_utils.log_service("ansible-playbook logic/transit/configure_transit.yml -i logic/inventory/hosts.yml -v --extra-vars '"+extra_vars+"'")
            rc = raas_utils.run_playbook("ansible-playbook logic/transit/configure_transit.yml -i logic/inventory/hosts.yml -v --extra-vars '"+extra_vars+"'")
            if (rc != 0):
                raise

            new_subnet=str(ipaddress.ip_address(subnet[0])+4) + '/' + subnet[1]
            raas_utils.update_veth_subnet('l2t_h',new_subnet)

            subnet = t_loopback_ip.split('/')
            new_subnet = str(ipaddress.ip_address(subnet[0])+1) + '/' + subnet[1]
            raas_utils.update_veth_subnet('loopbacks',new_subnet)
            raas_utils.log_client("l2 transit created successfully")
            raas_utils.log_service("l2_transit created successfully")

        except Exception as e:
            raas_utils.log_service("create transit failed "+ str(e))
            raas_utils.log_client("create transit failed")
            raise
    except Exception as e:
        raas_utils.log_service("create l2_transit failed python failed "+ str(e))
        raas_utils.log_client("create l2_transit failed")
