import re
from typing import Union, List, Any, Callable, TypeVar, Dict
from six import iteritems

from ._k8s_helper import K8sHelper
from .. import dsl

# generics
T = TypeVar('T')


def _get_pipelineparam_str(payload: str) -> List[str]:
    """Get a list of pipeline signatures from a string.
    
    Args:
        payload {str}: string
    """

    matches = re.findall(
        r'{{pipelineparam:op=([\w\s_-]*);name=([\w\s_-]+);value=(.*?)}}',
        payload)
    return [
        str(dsl.PipelineParam(x[1], x[0], x[2])) for x in list(set(matches))
    ]


def _sanitize_pipelineparam(param: dsl.PipelineParam):
    """Sanitize the name of a PipelineParam.
  
    Args:
      params: a PipelineParam to sanitize
    """
    return dsl.PipelineParam(
        K8sHelper.sanitize_k8s_name(param.name),
        K8sHelper.sanitize_k8s_name(param.op_name), param.value)


def _sanitize_pipelineparams(
        params: Union[dsl.PipelineParam, List[dsl.PipelineParam]]):
    """Sanitize the name(s) of a PipelineParam (or a list of PipelineParam).
  
    Args:
      params: a PipelineParam or a list of PipelineParam to sanitize
    """
    params = params if isinstance(params, list) else [params]
    return [_sanitize_pipelineparam(param) for param in params]


def _process_obj(obj: Any, map_to_tmpl_var: dict):
    """recursively sanitize any PipelineParam in the object.
    
    Args:
      obj: any obj that may have PipelineParam
      map_to_tmpl_var: a dict that maps an unsanitized pipeline
                       params signature into a template var
    """
    # serialized str might be unsanitized
    if isinstance(obj, str):
        # get signature
        pipeline_params_signs = _get_pipelineparam_str(obj)
        if not pipeline_params_signs:
            return obj
        # replace all unsanitized signature with template var
        for pattern in pipeline_params_signs:
            obj = re.sub(pattern, map_to_tmpl_var[pattern], obj)

    # list
    if isinstance(obj, list):
        return [_process_obj(item, map_to_tmpl_var) for item in obj]

    # tuple
    if isinstance(obj, tuple):
        return tuple((_process_obj(item, map_to_tmpl_var) for item in obj))

    # dict
    if isinstance(obj, dict):
        return {
            key: _process_obj(value, map_to_tmpl_var)
            for key, value in obj.items()
        }

    # pipelineparam
    if isinstance(obj, dsl.PipelineParam):
        # if not found in unsanitized map, then likely to be sanitized
        return map_to_tmpl_var.get(
            str(obj), '{{inputs.parameters.%s}}' % obj.full_name)

    # k8s_obj
    if hasattr(obj, 'swagger_types') and isinstance(obj.swagger_types, dict):
        # process everything inside recursively
        for key in obj.swagger_types.keys():
            setattr(obj, key, _process_obj(getattr(obj, key), map_to_tmpl_var))
        # return json representation of the k8s obj
        return K8sHelper.convert_k8s_obj_to_json(obj)

    # do nothing
    return obj


def _process_container_ops(op: dsl.ContainerOp):
    """Recursively go through the attrs listed in `attrs_with_pipelineparams` 
    and sanitize and replace pipeline params with template var string. 
    
    Returns a tuple[processed containerOp, sanitized inputs pipeparams]

    Args:
        op {dsl.ContainerOp}: class that inherits from ds.ContainerOp
    
    Returns:
        Tuple[dsl.ContainerOp, List[dsl.PipelineParams]]
    """

    # tmp map: unsanitized rpr -> sanitized PipelineParam
    _map = {str(param): _sanitize_pipelineparam(param) for param in op.inputs}

    # sanitized all inputs (some might come from serialized pipeline param strings)
    inputs = list(_map.values())

    # map: unsanitized pipeline param rpr -> template var string
    map_to_tmpl_var = {
        key: '{{inputs.parameters.%s}}' % param.full_name
        for key, param in _map.items()
    }

    # process all attr with pipelineParams except inputs and outputs parameters
    for key in op.attrs_with_pipelineparams:
        setattr(op, key, _process_obj(getattr(op, key), map_to_tmpl_var))

    return op, inputs


def _parameters_to_json(params: List[dsl.PipelineParam]):
    _to_json = (lambda param: dict(name=param.name, value=param.value)
                if param.value else dict(name=param.name))
    params = [_to_json(param) for param in params]
    # Sort to make the results deterministic.
    params.sort(key=lambda x: x['name'])
    return params


# TODO: artifacts
def _inputs_to_json(inputs_params: List[dsl.PipelineParam], _artifacts=None):
    return {'parameters': _parameters_to_json(inputs_params)}


def _outputs_to_json(outputs: Dict[str, dsl.PipelineParam],
                     file_outputs: Dict[str, str],
                     output_artifacts: List[dict]):
    output_parameters = []
    for param in outputs.values():
        output_parameters.append({
            'name': param.full_name,
            'valueFrom': {
                'path': file_outputs[param.name]
            }
        })
    output_parameters.sort(key=lambda x: x['name'])
    return {'parameters': output_parameters, 'artifacts': output_artifacts}


def _build_conventional_artifact(name):
    return {
        'name': name,
        'path': '/' + name + '.json',
        's3': {
            # TODO: parameterize namespace for minio service
            'endpoint': 'minio-service.kubeflow:9000',
            'bucket': 'mlpipeline',
            'key': 'runs/{{workflow.uid}}/{{pod.name}}/' + name + '.tgz',
            'insecure': True,
            'accessKeySecret': {
                'name': 'mlpipeline-minio-artifact',
                'key': 'accesskey',
            },
            'secretKeySecret': {
                'name': 'mlpipeline-minio-artifact',
                'key': 'secretkey'
            }
        },
    }

# TODO: generate argo python classes from swagger and use convert_k8s_obj_to_json
def _op_to_template(op: dsl.ContainerOp):
    """Generate template given an operator inherited from dsl.ContainerOp."""

    processed_op, sanitized_inputs = _process_container_ops(op)

    # default output artifacts
    output_artifacts = [
        _build_conventional_artifact(name)
        for name in ['mlpipeline-ui-metadata', 'mlpipeline-metrics']
    ]

    # workflow template
    template = {
        'name': op.name,
        'container': K8sHelper.convert_k8s_obj_to_json(op.container),
        'inputs': _inputs_to_json(sanitized_inputs),
        'outputs': _outputs_to_json(op.outputs, op.file_outputs,
                                    output_artifacts)
    }

    # node selector
    if processed_op.node_selector:
        template['nodeSelector'] = processed_op.node_selector

    # metadata
    if processed_op.pod_annotations or processed_op.pod_labels:
        template['metadata'] = {}
        if processed_op.pod_annotations:
            template['metadata']['annotations'] = processed_op.pod_annotations
        if processed_op.pod_labels:
            template['metadata']['labels'] = processed_op.pod_labels
    # retries
    if processed_op.num_retries:
        template['retryStrategy'] = {'limit': processed_op.num_retries}

    # sidecars
    if processed_op.sidecars:
        template['sidecars'] = processed_op.sidecars

    return template